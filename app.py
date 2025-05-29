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
import pandas as pd # For reading local Excel file

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

# --- Local Excel Configuration ---
LOCAL_EXCEL_FILE_PATH = "historic_data.xlsx"  # <<< --- YOU NEED TO CHANGE THIS if your file is named differently or elsewhere
EXCEL_SHEET_NAME = "Sheet1"                  # <<< --- YOU NEED TO CHANGE THIS if your sheet is named differently
EXCEL_CELL = "A1"                            # <<< --- YOU NEED TO CHANGE THIS if your data is in a different cell
# --- End Local Excel Configuration ---

def get_historic_data():
    """Fetches historic data for context from a local Excel file."""
    try:
        if not os.path.exists(LOCAL_EXCEL_FILE_PATH):
            logging.error(f"Local Excel file not found at: {LOCAL_EXCEL_FILE_PATH}")
            return "Error: Local historic data Excel file not found."

        # Read the specific cell from the Excel file
        # Use openpyxl engine for .xlsx files
        df = pd.read_excel(LOCAL_EXCEL_FILE_PATH,
                           sheet_name=EXCEL_SHEET_NAME,
                           header=None, # Treat the first row as data if no header
                           engine='openpyxl')
        
        # Try to get data from the specified cell (e.g., A1 -> row 0, col 0)
        # This requires a bit of care if EXCEL_CELL is like "A1", "B5" etc.
        # For simplicity, we'll assume A1 means the very first cell (0,0)
        # A more robust parser for cell notation might be needed for general cases.
        # For "A1", iloc[0,0] works if it's the first cell.
        # If EXCEL_CELL is, for example, B2, you'd need to map that to iloc[1,1].
        # Let's assume for this example EXCEL_CELL = "A1" maps to the first cell [0,0]
        # This part might need refinement based on how you want to specify the cell.
        
        # A simple way for common cell notation like "A1", "B2"
        col_str = "".join(filter(str.isalpha, EXCEL_CELL))
        row_str = "".join(filter(str.isdigit, EXCEL_CELL))
        
        if not col_str or not row_str:
            logging.error(f"Invalid Excel cell format: {EXCEL_CELL}. Expected format like 'A1'.")
            return "Error: Invalid Excel cell format for historic data."

        col_idx = sum([(ord(char.upper()) - ord('A') + 1) * (26**i) for i, char in enumerate(reversed(col_str))]) -1
        row_idx = int(row_str) - 1

        if row_idx < 0 or col_idx < 0 or row_idx >= len(df) or col_idx >= len(df.columns):
            logging.error(f"Cell {EXCEL_CELL} is out of bounds for the sheet dimensions.")
            return "Error: Historic data cell is out of bounds in Excel sheet."
            
        description = str(df.iloc[row_idx, col_idx])
        
        if pd.isna(description) or not description.strip():
             logging.warning(f"No data found in Excel file at {LOCAL_EXCEL_FILE_PATH}, sheet '{EXCEL_SHEET_NAME}', cell '{EXCEL_CELL}'.")
             return "No historical data found in the configured Excel cell."

        return description.strip()

    except FileNotFoundError:
        logging.error(f"Local Excel file not found at: {LOCAL_EXCEL_FILE_PATH}")
        return "Error: Local historic data Excel file not found."
    except Exception as e:
        logging.error(f"An unexpected error occurred while fetching local Excel data: {e}")
        return f"Unexpected error fetching local Excel data: {e}"

@app.event("file_shared")
def handle_file_shared_events(body, say, logger):
    """Handles file_shared events, specifically looking for images."""
    event = body.get("event", {})
    file_id = event.get("file_id")
    user_id = event.get("user_id")

    if not file_id:
        logger.error("File ID not found in file_shared event.")
        return

    logger.info(f"File shared: {file_id} by user {user_id}")

    try:
        # Get file info using Slack API to check file type and get download URL
        file_info_response = app.client.files_info(file=file_id)
        if not file_info_response.get("ok"):
            logger.error(f"Failed to get file info: {file_info_response.get('error')}")
            say(f"Sorry <@{user_id}>, I couldn't retrieve information about that file.")
            return

        file_data = file_info_response.get("file")
        mimetype = file_data.get("mimetype", "").lower()
        file_url_private = file_data.get("url_private_download")

        # Check if the file is an image
        if mimetype.startswith("image/"):
            logger.info(f"Processing image: {file_data.get('name')} ({mimetype})")

            if not file_url_private:
                logger.error("Private download URL not found for the image.")
                say(f"Sorry <@{user_id}>, I couldn't access the image file to download it.")
                return

            # Download the image
            headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
            response = requests.get(file_url_private, headers=headers, stream=True)
            response.raise_for_status() # Raise an exception for bad status codes

            # Convert image to base64
            img = Image.open(BytesIO(response.content))
            
            # Optional: Resize image if it's too large (OpenAI has limits)
            # max_size = (1024, 1024) # Example max dimensions
            # img.thumbnail(max_size, Image.LANCZOS)

            buffered = BytesIO()
            image_format = mimetype.split('/')[-1] # e.g., 'jpeg', 'png'
            if image_format == 'jpg': # common variation
                image_format = 'jpeg'
            
            # Ensure Pillow supports the format or default to PNG
            supported_formats_for_pillow_save = ["jpeg", "png", "gif", "bmp", "tiff"] # Common ones
            if image_format.lower() not in supported_formats_for_pillow_save:
                logger.warning(f"Original image format {image_format} might not be directly saveable by Pillow; defaulting to PNG for base64 encoding.")
                image_format = "png" # Default to PNG if format is unusual or not directly supported by Pillow's save for BytesIO

            img.save(buffered, format=image_format.upper())
            base64_image = base64.b64encode(buffered.getvalue()).decode("utf-8")
            
            historic_data = get_historic_data()
            prompt_text = f"Please review this image. Historical context: {historic_data}"

            say(f"Thanks <@{user_id}>! I've received your image. Processing it with AI now...")

            # Call OpenAI API
            try:
                chat_completion = openai_client.chat.completions.create(
                    model="gpt-4o", # Or gpt-4-turbo, gpt-4o-mini
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt_text},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{mimetype};base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=500
                )
                review = chat_completion.choices[0].message.content
                say(f"<@{user_id}>, here's the review:
{review}")
            except Exception as e:
                logger.error(f"Error calling OpenAI API: {e}")
                say(f"Sorry <@{user_id}>, I encountered an error while trying to get a review from OpenAI.")

        else:
            logger.info(f"File shared is not an image: {mimetype}. Skipping.")
            # Optionally, you can inform the user if they share a non-image file
            # say(f"<@{user_id}>, I can only process image files at the moment.")

    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading file: {e}")
        say(f"Sorry <@{user_id}>, I had trouble downloading the file.")
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        say(f"Sorry <@{user_id}>, an unexpected error occurred while processing your file.")


@app.event("app_mention")
def handle_app_mention_events(body, say, logger):
    """Handles mentions of the bot."""
    user_id = body["event"]["user"]
    text = body["event"]["text"]
    logger.info(f"Bot mentioned by {user_id}: {text}")
    say(f"Hi <@{user_id}>! You mentioned me. If you share an image, I can help review it.")

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