import os
from google import genai

project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "riduck-bike-course-simulator")
client = genai.Client(vertexai=True, project=project_id, location="asia-northeast3")

test_models = [
    "gemini-1.0-pro",
    "gemini-1.0-pro-001",
    "gemini-1.0-pro-002",
    "gemini-1.5-flash",
    "gemini-1.5-flash-001",
    "gemini-1.5-flash-002",
    "gemini-1.5-flash-preview-0514",
    "gemini-1.5-pro",
    "gemini-1.5-pro-001",
    "gemini-1.5-pro-002",
    "gemini-1.5-pro-preview-0514",
    "gemini-2.0-flash",
    "gemini-2.0-flash-exp",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-lite-preview-02-05",
    "gemini-2.0-pro-exp",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
    "gemini-3.0-flash",
    "gemini-3.0-pro",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-3.1-pro-preview",
]

available = []
for m in test_models:
    try:
        response = client.models.generate_content(
            model=m,
            contents="hi"
        )
        available.append(m)
        print(f"[OK] {m}")
    except Exception as e:
        err_msg = str(e)
        if "404" in err_msg or "not found" in err_msg.lower() or "400" in err_msg:
            # Not available or not found or model error
            pass
        else:
            print(f"[FAIL] {m} : {type(e).__name__} - {err_msg}")

print("\n--- Available models in asia-northeast3 ---")
for m in available:
    print(m)
