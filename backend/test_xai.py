import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.environ["XAI_API_KEY"],
    base_url="https://api.x.ai/v1",
)

print("=== Dostupni modeli ===")
for model in client.models.list().data:
    print(model.id)

print("\n=== Test chat completion ===")
response = client.chat.completions.create(
    model="grok-4",
    messages=[{"role": "user", "content": "Say hello in exactly 5 words."}],
)
print(response.choices[0].message.content)
