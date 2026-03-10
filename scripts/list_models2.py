import os
import google.auth
from google.cloud import aiplatform

credentials, project_id = google.auth.default()
aiplatform.init(project=project_id, location="asia-northeast3")

# We can also just list models via REST or the new genai SDK
from google import genai
client = genai.Client(vertexai=True, project=project_id, location="asia-northeast3")
for m in client.models.list():
    print(m.name)
