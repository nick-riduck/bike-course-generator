import os
from google import genai

try:
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "riduck-bike-course-simulator")
    print(f"Project: {project_id}")
    client = genai.Client(vertexai=True, project=project_id, location="asia-northeast3")
    models = list(client.models.list())
    print(f"Found {len(models)} models.")
    for m in models:
        print(m.name)
except Exception as e:
    print(f"Error: {e}")
