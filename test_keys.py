"""Test Groq API with version 1.5.0"""

import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 50)
print("Testing Groq API (v1.5.0)")
print("=" * 50)

groq_key = os.getenv("GROQ_API_KEY")
if not groq_key:
    print("❌ GROQ_API_KEY not found in .env")
    exit(1)

print(f"✅ API Key found: {groq_key[:20]}...")

try:
    from groq import Groq

    # ✅ Groq 1.5.0 accepts api_key directly
    client = Groq(api_key=groq_key)
    print("✅ Client created")

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say 'DocuMind API is working!'"}
        ],
        max_tokens=30,
        temperature=0.3
    )

    print("✅ SUCCESS!")
    print(f"📝 Response: {response.choices[0].message.content}")
    print(f"📊 Tokens used: {response.usage.total_tokens}")

except Exception as e:
    print(f"❌ Error: {e}")
    print(f"   Type: {type(e).__name__}")