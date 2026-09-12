"""Manual connectivity check for the xAI API. Run directly, not via pytest:

uv run python tests/test_xai_connection.py
"""

import os

from dotenv import load_dotenv
from openai import OpenAI


def main() -> None:
    load_dotenv()
    client = OpenAI(api_key=os.environ["XAI_API_KEY"], base_url="https://api.x.ai/v1")

    print("=== Available models ===")
    for model in client.models.list().data:
        print(model.id)

    print("\n=== Chat completion test ===")
    response = client.chat.completions.create(
        model="grok-4",
        messages=[{"role": "user", "content": "Say hello in exactly 5 words."}],
    )
    print(response.choices[0].message.content)


if __name__ == "__main__":
    main()
