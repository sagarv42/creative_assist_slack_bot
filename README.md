# Slack OpenAI Image Review Bot

This project is a Python-based Slack bot. When an image is uploaded to a designated Slack channel, the bot performs the following actions:
1.  Downloads the uploaded image.
2.  Collects a set of 'n' example images from a local directory.
3.  Reads corresponding performance data for these example images from a local CSV file.
4.  Sends the newly uploaded image, along with the 'n' example images and their performance data, to the OpenAI API (e.g., GPT-4o).
5.  The OpenAI model then reviews and scores the uploaded image, using the provided examples for context.
6.  Finally, the bot posts this AI-generated review and score back to the Slack channel.

## Features

*   **Slack Integration:**
    *   Connects to Slack using Socket Mode.
    *   Listens for `file_shared` events to detect new image uploads.
    *   Responds to `app_mention` events.
*   **Image Processing:**
    *   Downloads images shared in Slack.
    *   Reads and processes local example images.
    *   Encodes all images to base64 for API transmission.
*   **OpenAI Integration:**
    *   Utilizes the OpenAI API (e.g., `gpt-4o`) for comparative image analysis and review.
    *   Constructs complex prompts including multiple images (the target image and context examples) and associated textual data (performance info for examples).
*   **Local Context Data:**
    *   Reads example image filenames and their performance descriptions from a local CSV file.
    *   Loads example image files from a specified local directory.
*   **Development & Testing:**
    *   Includes a standalone script (`test_openai_vision.py`) to test basic OpenAI vision API integration with a single local image.

## Prerequisites

*   Python 3.8+
*   A Slack Workspace where you can create and install apps.
*   An OpenAI API Key with access to vision models (e.g., GPT-4o).
*   A local directory containing example images.
*   A local CSV file mapping example image filenames to their performance data.

## Project Structure

```
.
├── .env                    # For storing API keys and tokens (create this manually)
├── .gitignore              # Specifies intentionally untracked files that Git should ignore
├── app.py                  # Main Slack bot application logic
├── res/                    # Directory to store your example context images & CSV
│   ├── Img_1.jpg
│   ├── Img_2.png
│   └── Hack_Official_example.csv # CSV file with performance data for example images (create this manually)
├── requirements.txt        # Python dependencies
└── test_openai_vision.py   # Script to test OpenAI vision API with a single local image
```

## Setup Instructions

1.  **Clone the Repository (if applicable).**

2.  **Create a Python Virtual Environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Create `.env` File:**
    Create a file named `.env` in the project root and add your credentials:
    ```env
    SLACK_BOT_TOKEN="xoxb-your-slack-bot-token"
    SLACK_APP_TOKEN="xapp-your-slack-app-token-for-socket-mode"
    OPENAI_API_KEY="sk-your-openai-api-key"
    ```

5.  **Prepare Local Example Images and Performance CSV:**
    *   **Create `res/` directory:** In the project root, create a directory named `res` (or update `EXAMPLE_IMAGES_DIR` in `app.py` if you choose a different name/path).
    *   **Add Example Images:** Place your example image files (e.g., `.jpg`, `.png`) into this `res/` directory.
    *   **Create `Hack_Official_example.csv` in `res/`:** In the `res/` directory, create a CSV file named `Hack_Official_example.csv` (or update `EXAMPLE_PERFORMANCE_CSV` in `app.py`).
        *   This CSV must be **pipe-separated** (using `|` as the delimiter) and contain at least two columns: `image_filename` and `performance_info`.
        *   Example content for `Hack_Official_example.csv`:
            ```csv
            image_filename|performance_info
            example1.jpg|"Achieved high click-through rates (5%) and strong user engagement."
            example2.png|"Performed well in A/B tests for brand recall, but lower conversion."
            another_pic.jpeg|"Excellent for social media shares, mediocre on direct sales."
            ```
    *   **Configure `app.py` (if paths/settings differ from defaults):**
        *   Open `app.py`. The relevant constants are now at the top of the file:
            ```python
            EXAMPLE_IMAGES_DIR = "./res/"
            EXAMPLE_PERFORMANCE_CSV = "./res/Hack_Official_example.csv"
            NUM_EXAMPLES_TO_INCLUDE = 5 # Adjust how many examples are sent
            ```

6.  **Configure Slack App:**
    *   Go to your Slack app's settings page on `api.slack.com`.
    *   **Basic Information:**
        *   Ensure you have an "App-Level Token" generated with the `connections:write` scope. This is needed for Socket Mode and is used as `SLACK_APP_TOKEN` in your `.env` file.
    *   **Socket Mode:**
        *   Enable Socket Mode.
    *   **Event Subscriptions:**
        *   Enable events.
        *   Subscribe to Bot Events:
            *   `app_mention`: Allows your bot to receive an event when it's directly mentioned.
            *   `file_shared`: Allows your bot to receive an event when a file is shared in a channel it's a part of.
            *   *(Optional but Recommended for Robustness):* `message.channels` (or more specific `message.*` events like `message.im`, `message.mpim` if your bot operates in those contexts). This helps catch file shares that might arrive as generic messages with a `file_share` subtype, as handled in `app.py`.
    *   **OAuth & Permissions:**
        *   Navigate to the "OAuth & Permissions" page.
        *   Ensure the following Bot Token Scopes are added:
            *   `app_mentions:read`: Required for the `app_mention` event.
            *   `chat:write`: Allows your bot to send messages.
            *   `files:read`: Allows your bot to read files and their metadata (like download URLs).
            *   *(If using `message.*` events):* `channels:history`, `groups:history`, `im:history`, `mpim:history` might be needed depending on the specific `message.*` events you subscribe to, to allow the bot to see messages in those contexts. For the current `app.py` which can handle `message.channels` for file shares, `channels:history` is a good addition.

## Running the Bot

1.  **Activate Virtual Environment:**
    ```bash
    source .venv/bin/activate  # Or .venv\Scripts\activate on Windows
    ```

2.  **Run the Main Bot Application:**
    ```bash
    python app.py
    ```
    *   The bot will connect to Slack via Socket Mode. You should see log messages in your terminal.

3.  **Invite the Bot to Channels:** In Slack, invite your bot user to the channels where you want it to operate.

## Using the Bot

*   **Image Review:** Upload an image to a channel where the bot is a member. The bot will acknowledge the image, gather the local example images and their CSV data, and then post a review from OpenAI based on all this context.
*   **Mention:** Mention the bot (e.g., `@YourBotName hello`) to see its direct response.

## Testing OpenAI Vision Separately

The `test_openai_vision.py` script allows you to test image sending to OpenAI directly, without the Slack bot.

1.  **Ensure `OPENAI_API_KEY` is in your `.env` file.**
2.  **Ensure you have a `./test_image.png` file or modify the path in `test_openai_vision.py`.**
3.  **Run the test script:**
    ```bash
    python test_openai_vision.py
    ```
4.  The script will output the OpenAI API's description of the image.
