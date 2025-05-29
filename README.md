# Slack OpenAI Image Review Bot

This project is a Python-based Slack bot that listens for images shared in Slack channels. When an image is detected, the bot downloads it, sends it to the OpenAI API (specifically a vision-capable model like GPT-4o) along with contextual historical data fetched from a local Excel file, and then posts the AI-generated review back to the Slack channel.

## Features

*   **Slack Integration:**
    *   Connects to Slack using Socket Mode.
    *   Listens for `file_shared` events to detect new image uploads.
    *   Responds to `app_mention` events.
*   **Image Processing:**
    *   Downloads images shared in Slack.
    *   Encodes images to base64 for API transmission.
    *   Handles common image types (JPEG, PNG, GIF, WEBP) and attempts to default to PNG for others.
*   **OpenAI Integration:**
    *   Utilizes the OpenAI API (e.g., `gpt-4o`) for image analysis and review.
    *   Constructs prompts that include both the image and textual context.
*   **Local Excel File Integration:**
    *   Fetches historical/contextual data from a specified cell in a local Excel (`.xlsx`) file to provide richer context to the OpenAI model for reviews.
*   **Development & Testing:**
    *   Includes a standalone script (`test_openai_vision.py`) to test OpenAI vision API integration with local images independently of the Slack bot.

## Prerequisites

*   Python 3.8+
*   A Slack Workspace where you can create and install apps.
*   An OpenAI API Key with access to vision models (e.g., GPT-4o).
*   A local Excel file (e.g., `historic_data.xlsx`) containing the historical data for context.

## Project Structure

```
.
├── .env                    # For storing API keys and tokens (create this manually)
├── .gitignore              # Specifies intentionally untracked files that Git should ignore
├── app.py                  # Main Slack bot application logic
├── historic_data.xlsx      # Example: Local Excel file for historic data (create this manually)
├── requirements.txt        # Python dependencies
└── test_openai_vision.py   # Script to test OpenAI vision API with local images
```

## Setup Instructions

1.  **Clone the Repository (if applicable):**
    ```bash
    # git clone <your-repo-url>
    # cd <your-repo-name>
    ```

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
    *   Replace placeholder values with your actual tokens and API key.

5.  **Prepare Local Excel File for Historic Data:**
    *   Create an Excel file (e.g., `historic_data.xlsx`) in your project's root directory (or your preferred location).
    *   Add the historical data/contextual description to a specific cell within this Excel file (e.g., cell `A1` of `Sheet1`).
    *   Open `app.py` and update the following constants to match your Excel file setup:
        ```python
        LOCAL_EXCEL_FILE_PATH = "historic_data.xlsx"  # Path to your Excel file
        EXCEL_SHEET_NAME = "Sheet1"                  # Name of the sheet containing the data
        EXCEL_CELL = "A1"                            # Cell containing the historic data (e.g., "A1", "B5")
        ```

6.  **Configure Slack App:**
    *   Go to [https://api.slack.com/apps](https://api.slack.com/apps) and create a new app or use an existing one.
    *   **Enable Socket Mode:** In your app's settings under "Socket Mode", enable it. Generate an App-Level Token with the `connections:write` scope. This is your `SLACK_APP_TOKEN`.
    *   **OAuth & Permissions:** Under "OAuth & Permissions", add the following Bot Token Scopes:
        *   `app_mentions:read`
        *   `chat:write`
        *   `files:read`
        Your `SLACK_BOT_TOKEN` is the "Bot User OAuth Token" found on this page after installing the app to your workspace.
    *   **Event Subscriptions:** Under "Event Subscriptions", enable events.
        *   Subscribe to the following bot events:
            *   `app_mention`
            *   `file_shared`
    *   **App Home (Optional):** Enable the "Home Tab" under "App Home" settings for a better user experience if you plan to expand bot interactions there.
    *   **Install/Reinstall App:** Install (or reinstall if you made changes) the app to your Slack workspace.

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

*   **Image Review:** Upload an image to a channel where the bot is a member. The bot should acknowledge the image and then post a review from OpenAI, using context from your local Excel file.
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

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

Please make sure to update tests as appropriate.