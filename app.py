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
import time # Added for event deduplication

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

# --- Configuration for Example Images and Performance Data ---
EXAMPLE_IMAGES_DIR = "./res/"  # <<< --- YOU NEED TO CREATE THIS DIRECTORY AND ADD IMAGES
EXAMPLE_PERFORMANCE_CSV = "./res/Hack_Official_example.csv"  # <<< --- YOU NEED TO CREATE THIS CSV
NUM_EXAMPLES_TO_INCLUDE = 5  # Number of example images to include in the prompt
# Expected CSV columns: 'image_filename' (e.g., pic1.jpg), 'performance_info' (e.g., "High engagement, CTR 5%")
# --- End Example Images Configuration ---

# --- Globals for Event Deduplication ---
PROCESSED_EVENT_IDS = set()
MAX_EVENT_ID_AGE_SECONDS = 300  # 5 minutes, adjust as needed
EVENT_ID_TIMESTAMPS = {} # Stores event_id: arrival_time
# --- End Globals for Event Deduplication ---

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

        df = pd.read_csv(EXAMPLE_PERFORMANCE_CSV, delimiter='|')
        if 'image_filename' not in df.columns or 'performance_info' not in df.columns:
            logger.error(f"CSV must contain 'image_filename' and 'performance_info' columns (pipe-separated).")
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

@app.event("file_shared")
def handle_file_shared_events(body, say, logger):
    current_time = time.time()
    event_id = body.get("event_id")

    # --- Deduplication Logic ---
    # Clean up old event IDs from cache
    expired_ids = [
        eid for eid, ts in list(EVENT_ID_TIMESTAMPS.items()) 
        if current_time - ts > MAX_EVENT_ID_AGE_SECONDS
    ]
    for eid in expired_ids:
        PROCESSED_EVENT_IDS.discard(eid)
        if eid in EVENT_ID_TIMESTAMPS: # Check existence before del
            del EVENT_ID_TIMESTAMPS[eid]

    if event_id:
        if event_id in PROCESSED_EVENT_IDS:
            logger.info(f"handle_file_shared_events: Ignoring duplicate event_id: {event_id}")
            return
        PROCESSED_EVENT_IDS.add(event_id)
        EVENT_ID_TIMESTAMPS[event_id] = current_time
    else:
        # If no event_id, we can't deduplicate based on it. Proceed with caution.
        logger.warning("handle_file_shared_events: Event is missing an event_id. Cannot perform deduplication for this event.")
    # --- End Deduplication Logic ---

    event = body.get("event", {})
    user_id = event.get("user_id")
    file_id = event.get("file_id")
    channel_id = event.get("channel_id")
    original_event_ts = event.get("event_ts") # TS of the file_shared event itself

    logger.info(f"File shared event (ID: {event_id}): User '{user_id}', File '{file_id}', Channel '{channel_id}', Original TS '{original_event_ts}'")

    authorizations = body.get("authorizations", [])
    if authorizations and len(authorizations) > 0:
        bot_user_id_from_auth = authorizations[0].get("user_id")
        if user_id == bot_user_id_from_auth:
            logger.info(f"File {file_id} (Event ID: {event_id}) was shared by the bot itself ({user_id}). Ignoring event.")
            return

    if not all([user_id, file_id, channel_id, original_event_ts]): # original_event_ts needed as a fallback
        logger.error(
            f"File_shared event (ID: {event_id}) is missing critical information. "
            f"User: {user_id}, File: {file_id}, Channel: {channel_id}, Original TS: {original_event_ts}. Cannot reply properly."
        )
        if channel_id and user_id and file_id:
            try:
                # Using say for non-threaded fallback (missing info)
                say(
                    channel=channel_id,
                    text=f"Hi <@{user_id}>, I noticed you uploaded file. "
                         f"If you want me to review it, please @mention me directly with the file. Thanks!"
                )
                logger.info(f"Sent non-threaded fallback (missing info) using say to {user_id} in {channel_id} for file {file_id} (Event ID: {event_id}).")
            except Exception as e_post_fallback:
                logger.error(f"Error sending non-threaded fallback message (missing info) using say for event {event_id}: {e_post_fallback}")
        return

    # --- Attempt to get the actual message_ts for threading from files_info ---
    event_ts_to_use = original_event_ts # Default to original event_ts
    try:
        file_info_response = app.client.files_info(file=file_id)
        if file_info_response and file_info_response.get("ok"):
            file_data = file_info_response.get("file")
            if file_data and file_data.get("shares") and \
               isinstance(file_data["shares"].get("public"), dict) and \
               channel_id in file_data["shares"]["public"]:
                share_info_list = file_data["shares"]["public"][channel_id]
                if share_info_list and isinstance(share_info_list, list) and len(share_info_list) > 0:
                    # Taking the first share message in that channel. 
                    # Slack's behavior typically links the file_shared event to the most recent share message.
                    actual_message_ts = share_info_list[0].get("ts")
                    if actual_message_ts:
                        event_ts_to_use = actual_message_ts
                        logger.info(f"Using actual message_ts '{actual_message_ts}' from files_info for threading file {file_id} (Event ID: {event_id}).")
                    else:
                        logger.warning(f"Could not find 'ts' in share_info for file {file_id} in channel {channel_id}. Will use original event_ts '{original_event_ts}'. Event ID: {event_id}")
                else:
                    logger.warning(f"Share_info_list empty or not a list for file {file_id} in channel {channel_id}. Will use original event_ts '{original_event_ts}'. Event ID: {event_id}")
            else:
                logger.warning(f"No public shares found for file {file_id} in channel {channel_id}, or shares format unexpected. Will use original event_ts '{original_event_ts}'. Event ID: {event_id}")
        else:
            logger.error(f"Failed to get file_info for {file_id}: {file_info_response.get('error', 'Unknown error') if file_info_response else 'No response'}. Event ID: {event_id}")
    except Exception as e_fi:
        logger.error(f"Error calling files_info for {file_id} (Event ID: {event_id}): {e_fi}. Will use original event_ts '{original_event_ts}'.")
    # --- End files_info logic ---

    reply_message = (
        f"Hi <@{user_id}>, I see you uploaded a file. "
        f"If you'd like me to review it, please mention me with `@Creative Scoring Bot` directly along with the file. Thanks!"
    )

    try:
        # Using say for the primary threaded message
        say(
            channel=channel_id,
            text=reply_message,
            thread_ts=event_ts_to_use
        )
        logger.info(f"Sent THREADED guidance (using say, ts: {event_ts_to_use}) to user {user_id} in channel {channel_id} for file {file_id} (Event ID: {event_id}).")
    except Exception as e:
        logger.error(f"Error sending THREADED message (using say, ts: {event_ts_to_use}) for file_shared event {event_id}: {e}")
        try:
            # Using say for non-threaded fallback after primary send error
            say(
                channel=channel_id,
                text=f"Sorry <@{user_id}>, I tried to reply in a thread about your file `{file_id}` but encountered an issue. "
                     f"Please @mention me directly with the file for a review. Thanks! (Details: Could not thread using {event_ts_to_use})"
            )
            logger.info(f"Sent NON-THREADED fallback (using say) after threaded send failed for file {file_id} (Event ID: {event_id}) to user {user_id}.")
        except Exception as e_fallback_critical:
            logger.error(f"Error sending critical NON-THREADED fallback message (using say) for event {event_id}: {e_fallback_critical}")

@app.event("app_mention")
def handle_app_mention_events(body, say, logger):
    """Handles mentions of the bot. If a file is included in the mention, it processes the file."""
    event = body["event"]
    user_id = event["user"]
    text = event.get("text", "") # Get text, default to empty string if not present
    channel_id = event.get("channel")
    thread_ts_to_reply = event.get("event_ts") # Use event_ts of the mention to start/reply in a thread

    logger.info(f"handle_app_mention_events: Bot mentioned by {user_id}: {text} in channel {channel_id} (event_ts for threading: {thread_ts_to_reply})")

    if not channel_id or not thread_ts_to_reply:
        logger.error(f"Could not determine channel_id ({channel_id}) or thread_ts ({thread_ts_to_reply}) for app_mention reply. Event: {event}")
        # Cannot reply without channel_id, and threading is desired
        return

    # Check if files were uploaded with the mention
    uploaded_files = event.get("files")
    if uploaded_files and isinstance(uploaded_files, list) and len(uploaded_files) > 0:
        file_id = uploaded_files[0].get("id") # Get ID of the first file

        if not file_id:
            logger.error(f"App mention by {user_id} included files, but file_id was missing. Files: {uploaded_files}")
            say(f"Sorry <@{user_id}>, I saw you uploaded a file with your mention, but I couldn't get its ID.", channel=channel_id, thread_ts=thread_ts_to_reply)
            return

        logger.info(f"App mention by {user_id} in channel {channel_id} included file_id: {file_id}. Processing image...")
        # --- Start of image processing logic (adapted from handle_file_shared_events) ---
        try:
            file_info_response = app.client.files_info(file=file_id)
            if not file_info_response.get("ok"):
                logger.error(f"Failed to get file info for {file_id}: {file_info_response.get('error')}")
                say(text=f"Sorry <@{user_id}>, I couldn't retrieve information about the file you shared with your mention.", channel=channel_id, thread_ts=thread_ts_to_reply)
                return

            file_data = file_info_response.get("file")
            slack_mimetype = file_data.get("mimetype", "").lower()
            file_url_private = file_data.get("url_private_download")

            if slack_mimetype.startswith("image/"):
                logger.info(f"Processing uploaded image: {file_data.get('name')} ({slack_mimetype}) from app_mention.")

                if not file_url_private:
                    logger.error(f"Private download URL not found for the image {file_id} in app_mention.")
                    say(text=f"Sorry <@{user_id}>, I couldn't access the image file you shared with your mention.", channel=channel_id, thread_ts=thread_ts_to_reply)
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
                
                say(text=f"Thanks <@{user_id}>! I've received your image with your mention. Analyzing it with contextual examples...", channel=channel_id, thread_ts=thread_ts_to_reply)

                example_contexts = get_example_context_data(logger)

                main_prompt_instructions = (
                    "You are a creative performance analyst evaluating mobile or desktop ad creatives.\\n"
                    "Your task:\\n"
                    "1. Estimate a creative score from 0–100 based on likely ad performance\\n"
                    "2. Highlight 1–2 visual strengths\\n"
                    "3. Call out 1–2 weaknesses\\n"
                    "4. Suggest 2–3 specific improvements\\n"
                    "5. Summarize the image data that informed your decision\\n"
                    "Be concise but human. Focus on clarity, visual hierarchy, and user impact—not just aesthetics.\\n"
                    "---\\n"
                    "Please review and score this image based on its visual characteristics\\n"
                    "Respond in this exact format:\\n"
                    "--> Score: ##/100\\n"
                    "--> Strengths:\\n"
                    "• [1-line bullet]\\n"
                    "• [Optional 2nd bullet]\\n"
                    "-->  Weaknesses:\\n"
                    "• [1-line bullet]\\n"
                    "• [Optional 2nd bullet]\\n"
                    "--> Suggestions:\\n"
                    "• [Change 1]\\n"
                    "• [Change 2]\\n"
                    "• [Optional Change 3]\\n"
                    "--> Image Data Summary:\\n"
                    "---"
                )
                prompt_messages_content = [
                    {"type": "text", "text": main_prompt_instructions},
                    {"type": "image_url", "image_url": {"url": f"data:{uploaded_image_mimetype};base64,{base64_uploaded_image}"}}
                ]

                if not example_contexts:
                    logger.warning("No example contexts found for app_mention image review.")
                    prompt_messages_content.append({
                        "type": "text",
                        "text": "Historic Data for scoring:\\n• No example data was available for this review."
                    })
                else:
                    historic_data_header = "Historic Data for scoring:"
                    example_data_texts = []
                    for i, ex_data in enumerate(example_contexts):
                        example_data_texts.append(
                            f"--- Example {i+1} (Filename: {ex_data['filename']}) ---\\nPerformance Info: {ex_data['performance_info']}\\n--- End Example {i+1} ---"
                        )
                        example_data_texts.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:{ex_data['mime_type']};base64,{ex_data['base64_image']}"}
                        })
                    prompt_messages_content.append({"type": "text", "text": historic_data_header})
                    prompt_messages_content.extend(example_data_texts)

                try:
                    chat_completion = openai_client.chat.completions.create(
                        model="gpt-4o", 
                        messages=[{"role": "user", "content": prompt_messages_content}],
                        max_tokens=1000
                    )
                    review = chat_completion.choices[0].message.content
                    say(text=f"<@{user_id}>, here's the review for your image \"{file_data.get('name')}\":\\n{review}", channel=channel_id, thread_ts=thread_ts_to_reply)
                except Exception as e:
                    logger.error(f"Error calling OpenAI API during app_mention: {e}")
                    say(text=f"Sorry <@{user_id}>, I encountered an error with the AI review for the image in your mention.", channel=channel_id, thread_ts=thread_ts_to_reply)
            else:
                logger.info(f"File {file_id} shared with app_mention by {user_id} is not an image: {slack_mimetype}. Replying with help text.")
                say(text=f"Hi <@{user_id}>! You mentioned me with a file, but I can only process image files. Please try mentioning me with an image.", channel=channel_id, thread_ts=thread_ts_to_reply)
        except requests.exceptions.RequestException as e:
            logger.error(f"Error downloading file {file_id} from app_mention: {e}")
            say(text=f"Sorry <@{user_id}>, I had trouble downloading the file you shared with your mention.", channel=channel_id, thread_ts=thread_ts_to_reply)
        except Exception as e:
            logger.error(f"Error processing file {file_id} from app_mention: {e}")
            say(text=f"Sorry <@{user_id}>, an unexpected error occurred while processing the file in your mention.", channel=channel_id, thread_ts=thread_ts_to_reply)
        # --- End of image processing logic ---
    else:
        # No files attached to the mention, just a simple mention
        say(f"Hi <@{user_id}>! You mentioned me. If you share an image when you mention me, I can help review it.", channel=channel_id, thread_ts=thread_ts_to_reply)

# Add this handler if you want to acknowledge/log other message types or subtypes
# without them showing as "unhandled".
@app.event("message")
def handle_generic_message_events(body, logger, say):
    event = body.get("event", {})
    event_subtype = event.get("subtype")
    text = event.get("text", "")
    authorizations = body.get("authorizations", [])
    bot_id = authorizations[0].get("user_id") if authorizations else None

    if event.get("user") == bot_id or event.get("bot_id") is not None:
        return
        
    if event_subtype == "file_share":
        logger.info(f"handle_generic_message_events: Detected standalone file_share subtype by user {event.get('user')}. This is now ignored as primary processing happens via app_mention with files.")
        return 

    if bot_id and f"<@{bot_id}>" in text:
        logger.info(f"handle_generic_message_events: Ignoring message with mention as it should be handled by app_mention: {text}")
        return

    if event_subtype == "message_deleted":
        return
    
    if event_subtype is not None:
        logger.info(f"handle_generic_message_events: Received a message event with unhandled subtype: {event_subtype}")
        logger.info(body)
        return 

    logger.info(f"handle_generic_message_events: Received a generic message (not a mention, file_share, or known unhandled subtype) by user {event.get('user')}:")
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