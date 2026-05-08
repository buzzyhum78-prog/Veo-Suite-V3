from google import genai
import os

# Lấy API Key từ môi trường hoặc hardcode tạm để test
api_key = os.environ.get("GEMINI_API_KEY", "YOUR_KEY_HERE") 

try:
    client = genai.Client(api_key=api_key)
    print("--- AVAILABLE MODELS ---")
    for m in client.models.list():
        if "imagen" in m.name.lower():
            print(f"Name: {m.name} | Display: {m.display_name}")
except Exception as e:
    print(f"Error: {e}")
