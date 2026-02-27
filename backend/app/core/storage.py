import os
from google.cloud import storage
from app.core.config import STORAGE_TYPE, STORAGE_BASE_DIR, GCS_BUCKET_NAME

def save_to_storage(content: bytes, folder: str, filename: str):
    """
    Abstracted file saving logic. Supports LOCAL and GCS.
    Returns the relative path or URL for DB storage.
    """
    if STORAGE_TYPE == "LOCAL":
        full_dir = os.path.join(STORAGE_BASE_DIR, folder)
        os.makedirs(full_dir, exist_ok=True)
        file_path = os.path.join(full_dir, filename)
        with open(file_path, "wb") as f:
            f.write(content)
        return os.path.join(folder, filename)
    
    elif STORAGE_TYPE == "GCS":
        try:
            client = storage.Client()
            bucket = client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(f"{folder}/{filename}")
            
            content_type = "application/octet-stream"
            if filename.endswith(".png"):
                content_type = "image/png"
            elif filename.endswith(".json"):
                content_type = "application/json"
            
            blob.upload_from_string(content, content_type=content_type)
            
            if folder == "thumbnails":
                return f"/api/thumbnails/{filename}"
            
            return f"{folder}/{filename}"
        except Exception as e:
            print(f"GCS Upload Error: {e}")
            raise e
    
    return None
