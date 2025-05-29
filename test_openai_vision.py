import os
import base64
from openai import OpenAI
from dotenv import load_dotenv
from PIL import Image # To determine image type
import io

# Load environment variables from .env file
load_dotenv()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    print("Error: OPENAI_API_KEY not found in environment variables.")
    print("Please ensure it is set in your .env file.")
    exit()

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

def encode_image_to_base64(image_path):
    """Encodes a local image file to a base64 string and determines its MIME type."""
    try:
        with open(image_path, "rb") as image_file:
            # Read the image into memory to determine format with Pillow
            image_bytes = image_file.read()
            pil_image = Image.open(io.BytesIO(image_bytes))
            image_format = pil_image.format.lower()
            
            if image_format == 'jpeg' or image_format == 'jpg':
                mime_type = "image/jpeg"
            elif image_format == 'png':
                mime_type = "image/png"
            elif image_format == 'gif':
                mime_type = "image/gif"
            elif image_format == 'webp':
                mime_type = "image/webp"
            else:
                # Fallback or raise error if format is not commonly supported for web/API
                print(f"Warning: Detected image format '{image_format}' may not be optimally supported. Attempting with image/png.")
                mime_type = "image/png" # Defaulting to PNG as a common safe bet
            
            base64_image = base64.b64encode(image_bytes).decode("utf-8")
            return f"data:{mime_type};base64,{base64_image}"
    except FileNotFoundError:
        print(f"Error: Image file not found at {image_path}")
        return None
    except Exception as e:
        print(f"Error encoding image: {e}")
        return None

def main():
    image_path = "./test_image.png"
    if not os.path.exists(image_path):
        print(f"Error: The file '{image_path}' does not exist. Please check the path.")
        return

    base64_image_data_url = encode_image_to_base64(image_path)

    if not base64_image_data_url:
        return

    prompt_text = "What is in this image? Describe it in detail."
    print(f"\nSending image '{image_path}' to OpenAI with prompt: '{prompt_text}'")

    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # Or "gpt-4-vision-preview" if you prefer
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": base64_image_data_url
                            }
                        }
                    ]
                }
            ],
            max_tokens=300
        )
        print("\n--- OpenAI Response ---")
        print(response.choices[0].message.content)
        print("-----------------------")

    except Exception as e:
        print(f"\nAn error occurred while calling the OpenAI API: {e}")

if __name__ == "__main__":
    main() 