import os
from google import genai

project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "riduck-bike-course-simulator")
client = genai.Client(vertexai=True, project=project_id, location="asia-northeast3")
for m in client.models.list():
    if "gemini" in m.name:
        print(m.name)
