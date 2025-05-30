import os
import logging
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from openai import OpenAI
import requests
from io import BytesIO
from PIL import Image
import base64
import pandas as pd # For reading local Excel/CSV file
import random # For selecting example images

# Configure logging
logging.basicConfig(level=logging.INFO)

# Load environment variables from .env file
load_dotenv()

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN") # Needed for Socket Mode
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Initialize Slack Bolt app
# For Socket Mode, SLACK_APP_TOKEN is required.
# If you are not using Socket Mode (e.g., you have a public URL for event subscriptions),
# you would initialize with: app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
# Make sure to also get SLACK_SIGNING_SECRET from your Slack app's "Basic Information" page if not using Socket Mode.
app = App(token=SLACK_BOT_TOKEN)

# Initialize OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# --- Local Excel/CSV Configuration for Historic Data ---
# (Commented out or remove if not used for single historic text block)
# LOCAL_EXCEL_FILE_PATH = "historic_data.xlsx"
# EXCEL_SHEET_NAME = "Sheet1"
# EXCEL_CELL = "A1"

# --- Configuration for Example Images and Performance Data ---
EXAMPLE_IMAGES_DIR = "./example_images/"  # <<< --- YOU NEED TO CREATE THIS DIRECTORY AND ADD IMAGES
EXAMPLE_PERFORMANCE_CSV = "./example_performance.csv"  # <<< --- YOU NEED TO CREATE THIS CSV
NUM_EXAMPLES_TO_INCLUDE = 3  # Number of example images to include in the prompt
# Expected CSV columns: 'image_filename' (e.g., pic1.jpg), 'performance_info' (e.g., "High engagement, CTR 5%")
# --- End Example Images Configuration ---

def get_example_context_data(logger):
    """Fetches 'n' example images and their performance data."""
    examples = []
    try:
        if not os.path.exists(EXAMPLE_PERFORMANCE_CSV):
            logger.error(f"Example performance CSV not found at: {EXAMPLE_PERFORMANCE_CSV}")
            return []
        if not os.path.isdir(EXAMPLE_IMAGES_DIR):
            logger.error(f"Example images directory not found at: {EXAMPLE_IMAGES_DIR}")
            return []

        df = pd.read_csv(EXAMPLE_PERFORMANCE_CSV)
        if 'image_filename' not in df.columns or 'performance_info' not in df.columns:
            logger.error(f"CSV must contain 'image_filename' and 'performance_info' columns.")
            return []

        if len(df) == 0:
            logger.warning("Performance CSV is empty.")
            return []

        # Select N random examples (or first N if fewer than N available)
        num_to_sample = min(NUM_EXAMPLES_TO_INCLUDE, len(df))
        sampled_df = df.sample(n=num_to_sample) if len(df) >= num_to_sample else df

        for _, row in sampled_df.iterrows():
            image_filename = row['image_filename']
            performance_info = row['performance_info']
            image_path = os.path.join(EXAMPLE_IMAGES_DIR, image_filename)

            if not os.path.exists(image_path):
                logger.warning(f"Example image file not found: {image_path}. Skipping.")
                continue

            try:
                with open(image_path, "rb") as image_file:
                    img_bytes = image_file.read()
                    pil_image = Image.open(BytesIO(img_bytes))
                    img_format = pil_image.format.lower()
                    
                    mime_type = f"image/{img_format}"
                    if img_format == 'jpg': mime_type = "image/jpeg"
                    # Add more specific mimetypes if needed, or rely on common ones

                    base64_image = base64.b64encode(img_bytes).decode("utf-8")
                    examples.append({
                        "filename": image_filename,
                        "performance_info": performance_info,
                        "base64_image": base64_image,
                        "mime_type": mime_type
                    })
            except Exception as e:
                logger.error(f"Error processing example image {image_path}: {e}")
        
        logger.info(f"Prepared {len(examples)} examples for context.")
        return examples

    except Exception as e:
        logger.error(f"Error preparing example context data: {e}")
        return []

# Old get_historic_data function (can be removed or kept if you want both functionalities)
# def get_historic_data():
#     """Fetches historic data for context from a local Excel file."""
#     # ... (implementation for reading single text block from Excel)
#     pass 

@app.event("file_shared")
def handle_file_shared_events(body, say, logger):
    """Handles file_shared events, processing the uploaded image with context from other examples."""
    event = body.get("event", {})
    logger.info(f"--- Raw file_shared event data (called from @app.event('file_shared') or delegated) ---") 
    logger.info(event)
    logger.info(f"----------------------------------")

    # MODIFICATION POINT 2: Get file_id robustly
    file_id = event.get("file_id") 
    if not file_id and event.get("files") and isinstance(event.get("files"), list) and len(event.get("files")) > 0:
        # This handles the case where the event is a message subtype 'file_share'
        file_id = event.get("files")[0].get("id")

    user_id = event.get("user") # In message events, it's event.user, not event.user_id
    if not user_id: user_id = event.get("user_id") # Fallback for direct file_shared event type
    
    channel_id = event.get("channel") # In message events, it's event.channel
    if not channel_id: channel_id = event.get("channel_id") # Fallback for direct file_shared event type

    thread_ts_to_reply = event.get("event_ts") # This should be correct for both message subtype and direct event
    if not thread_ts_to_reply: thread_ts_to_reply = event.get("ts") # Fallback for message.ts if event_ts is missing

    if not file_id:
        logger.error("File ID not found in file_shared event (after checking event.file_id and event.files[0].id). Event dump:")
        logger.error(event)
        return
    
    if not channel_id or not thread_ts_to_reply:
        logger.error(f"Could not determine channel_id ({channel_id}) or thread_ts ({thread_ts_to_reply}) for replying.")
        # Fallback to just saying in channel if essential threading info is missing
        say(text=f"Sorry <@{user_id}>, there was an issue processing your file notification (missing channel/ts).", channel=channel_id or None)
        return

    logger.info(f"File shared: {file_id} by user {user_id} in channel {channel_id} (event_ts for threading: {thread_ts_to_reply})") # LOG 2: Log processed ts

    try:
        file_info_response = app.client.files_info(file=file_id)
        if not file_info_response.get("ok"):
            logger.error(f"Failed to get file info: {file_info_response.get('error')}")
            say(text=f"Sorry <@{user_id}>, I couldn't retrieve information about that file.", channel=channel_id, thread_ts=thread_ts_to_reply)
            return

        file_data = file_info_response.get("file")
        slack_mimetype = file_data.get("mimetype", "").lower()
        file_url_private = file_data.get("url_private_download")

        if slack_mimetype.startswith("image/"):
            logger.info(f"Processing uploaded image: {file_data.get('name')} ({slack_mimetype})")

            if not file_url_private:
                logger.error("Private download URL not found for the uploaded image.")
                say(text=f"Sorry <@{user_id}>, I couldn't access the uploaded image file.", channel=channel_id, thread_ts=thread_ts_to_reply)
                return

            headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
            response = requests.get(file_url_private, headers=headers, stream=True)
            response.raise_for_status()

            uploaded_image_bytes = response.content
            uploaded_pil_image = Image.open(BytesIO(uploaded_image_bytes))
            uploaded_image_format = uploaded_pil_image.format.lower()
            uploaded_image_mimetype = f"image/{uploaded_image_format}"
            if uploaded_image_format == 'jpg': uploaded_image_mimetype = "image/jpeg"

            base64_uploaded_image = base64.b64encode(uploaded_image_bytes).decode("utf-8")
            
            logger.info(f"Attempting to say initial ack in thread: {thread_ts_to_reply} in channel: {channel_id}") # LOG 3: Log before say
            say(text=f"Thanks <@{user_id}>! I've received your image. Gathering context and sending to AI for review...", channel=channel_id, thread_ts=thread_ts_to_reply)

            example_contexts = get_example_context_data(logger)

            prompt_messages_content = [
                {
                    "type": "text",
                    "text": f"Please review and score the primary image (the first image presented) based on its visual characteristics and in the context of the following {len(example_contexts)} example images and their performance data. Provide a score (e.g., out of 10) and a brief rationale."
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{uploaded_image_mimetype};base64,{base64_uploaded_image}"}
                }
            ]

            if not example_contexts:
                logger.warning("No example contexts found. Proceeding with only the uploaded image.")
                prompt_messages_content[0]["text"] = "Please review and score this image based on its visual characteristics. Provide a score (e.g., out of 10) and a brief rationale as no example data was available."
            else:
                for i, ex_data in enumerate(example_contexts):
                    prompt_messages_content.append({
                        "type": "text",
                        "text": f"Example {i+1} (Filename: {ex_data['filename']}): Performance Info - {ex_data['performance_info']}"
                    })
                    prompt_messages_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{ex_data['mime_type']};base64,{ex_data['base64_image']}"}
                    })
            
            try:
                chat_completion = openai_client.chat.completions.create(
                    model="gpt-4o", 
                    messages=[{
                        "role": "user",
                        "content": prompt_messages_content
                    }],
                    max_tokens=700 
                )
                review = chat_completion.choices[0].message.content
                logger.info(f"Attempting to say final review in thread: {thread_ts_to_reply} in channel: {channel_id}") # LOG 4: Log before final say
                say(text=f"<@{user_id}>, here's the review for your image \"{file_data.get('name')}\":\n{review}", channel=channel_id, thread_ts=thread_ts_to_reply)
            except Exception as e:
                logger.error(f"Error calling OpenAI API: {e}")
                say(text=f"Sorry <@{user_id}>, I encountered an error with the AI review.", channel=channel_id, thread_ts=thread_ts_to_reply)

        else:
            logger.info(f"File shared is not an image: {slack_mimetype}. Skipping.")
            # say(text=f"<@{user_id}>, I can only process image files. The file you shared was a {slack_mimetype}.", channel=channel_id, thread_ts=thread_ts_to_reply)

    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading file: {e}")
        say(text=f"Sorry <@{user_id}>, I had trouble downloading the file.", channel=channel_id, thread_ts=thread_ts_to_reply)
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        say(text=f"Sorry <@{user_id}>, an unexpected error occurred.", channel=channel_id, thread_ts=thread_ts_to_reply)


@app.event("app_mention")
def handle_app_mention_events(body, say, logger):
    """Handles mentions of the bot."""
    event = body["event"]
    user_id = event["user"]
    text = event["text"]
    # To avoid double processing if a generic message handler also exists for app mentions
    # we can check if this specific event was already processed by another handler if needed,
    # but Bolt usually handles specificity well. The main issue is usually duplicate event subscriptions.
    logger.info(f"handle_app_mention_events: Bot mentioned by {user_id}: {text} in channel {event.get('channel')}")
    say(f"Hi <@{user_id}>! You mentioned me. If you share an image, I can help review it.") # This say does not need thread_ts unless the mention itself was in a thread and you want to continue it.

# Add this handler if you want to acknowledge/log other message types or subtypes
# without them showing as "unhandled".
@app.event("message")
def handle_generic_message_events(body, logger, say):
    event = body.get("event", {})
    event_type = event.get("type")
    event_subtype = event.get("subtype")
    text = event.get("text", "")
    # Ensure authorizations is a list and has at least one element before accessing
    authorizations = body.get("authorizations", [])
    bot_id = authorizations[0].get("user_id") if authorizations else None

    # Check if it's a message from the bot itself to avoid loops
    if event.get("user") == bot_id or event.get("bot_id") is not None:
        # logger.info("handle_generic_message_events: Ignoring event from bot itself.")
        return
        
    # If it's a file_share message subtype, let the dedicated file_shared handler process it.
    if event_subtype == "file_share":
        logger.info(f"handle_generic_message_events: Detected file_share subtype. Attempting to delegate to handle_file_shared_events.")
        # The handle_file_shared_events expects `body`, `say`, `logger`
        # We need to ensure the `event` within the body for `handle_file_shared_events` is the one 
        # that `file_shared` expects, which is usually the `files[0]` info combined with user/channel.
        # For simplicity and directness, since file_shared handler already parses `event` from `body`,
        # we can just call it directly. The `file_shared` handler will look into `event['files']` itself.
        # However, the `@app.event('file_shared')` handler expects an event of type 'file_shared', not 'message'.
        # So, we need to simulate the call or, better, refactor the core logic.
        
        # Let's call the file_shared_events logic directly if it's a file_share subtype
        # We are essentially saying: if this generic message is a file share, run the file share logic.
        # This bypasses the need for a separate @app.event("file_shared") if Slack consistently sends it this way.
        # Alternatively, if @app.event("file_shared") IS working for some file shares, this might cause double processing.
        # We will rely on the file_id to be present in the event['files'][0]['id'] as per Slack's structure for file_share subtype.
        
        # Check if there are files in the event, which is expected for file_share subtype
        if event.get("files") and isinstance(event.get("files"), list) and len(event.get("files")) > 0:
            # The handle_file_shared_events function is designed to be called by the Bolt framework
            # with a specific structure for the `body` and `event` when the event type is `file_shared`.
            # Here, the event type is `message` with `subtype: 'file_shared'`.
            # The `event` object within the `body` for a `message` event with `subtype: 'file_shared'`
            # is slightly different from a direct `file_shared` event type's event object.
            # Specifically, the file_id is inside event['files'][0]['id'] for this message subtype.
            # The original `@app.event('file_shared')` handler expects `event['file_id']`.
            
            # Simplest is to call the main logic of handle_file_shared_events directly, 
            # passing the necessary parts or the whole body, and ensuring the logic inside 
            # handle_file_shared_events can find `file_id` from `event['files'][0]['id']`
            # For now, let's just call it, assuming the current handle_file_shared_events
            # correctly gets file_id from event.get("file_id") or event.get("files")[0].get("id")
            # The current handle_file_shared_events is already trying event.get("file_id")
            # Let's adjust `handle_file_shared_events` to also check `event['files'][0]['id']`
            return handle_file_shared_events(body, say, logger) #<<<< MODIFICATION POINT 1
        else:
            logger.warning("handle_generic_message_events: file_share subtype detected, but no files array found or empty.")
            return

    # Check if the text contains a mention of the bot. 
    if bot_id and f"<@{bot_id}>" in text:
        logger.info(f"handle_generic_message_events: Ignoring message with mention as it should be handled by app_mention: {text}")
        return

    if event_subtype == "message_deleted":
        # logger.info(f"handle_generic_message_events: Ignoring deleted message event.")
        return
    
    if event_subtype is not None:
        logger.info(f"handle_generic_message_events: Received a message event with subtype: {event_subtype}")
        logger.info(body)
        return 

    logger.info(f"handle_generic_message_events: Received a generic message (not a mention, file_share, or known subtype):")
    logger.info(body)


# Start your app
if __name__ == "__main__":
    # SocketModeHandler is common for development as it doesn't require a public URL.
    # For production, you might use a different way to start the app (e.g., a web server like Gunicorn).
    # Ensure SLACK_APP_TOKEN is set in your .env file for Socket Mode.
    if SLACK_APP_TOKEN and SLACK_BOT_TOKEN and OPENAI_API_KEY:
        handler = SocketModeHandler(app, SLACK_APP_TOKEN)
        handler.start()
    else:
        logging.error("Missing one or more required environment variables: SLACK_BOT_TOKEN, SLACK_APP_TOKEN, OPENAI_API_KEY")
        print("Error: Ensure SLACK_BOT_TOKEN, SLACK_APP_TOKEN, and OPENAI_API_KEY are set in your .env file.") 