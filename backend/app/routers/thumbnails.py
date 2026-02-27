import os
from fastapi import APIRouter, HTTPException, Response
from google.cloud import storage
from app.core.config import STORAGE_TYPE, STORAGE_BASE_DIR, GCS_BUCKET_NAME

router = APIRouter(prefix="/api/thumbnails", tags=["thumbnails"])

@router.get("/{filename}")
async def get_thumbnail_proxy(filename: str):
    """
    Proxy endpoint to serve thumbnails from GCS or Local storage.
    Ensures images are visible even if GCS bucket is private.
    """
    if STORAGE_TYPE == "GCS":
        try:
            client = storage.Client()
            bucket = client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(f"thumbnails/{filename}")
            
            if not blob.exists():
                raise HTTPException(status_code=404, detail="Thumbnail not found in GCS")
            
            content = blob.download_as_bytes()
            return Response(content=content, media_type="image/png")
        except Exception as e:
            print(f"GCS Proxy Error: {e}")
            raise HTTPException(status_code=500, detail="Error fetching image from GCS")
    
    else: # LOCAL
        file_path = os.path.join(STORAGE_BASE_DIR, "thumbnails", filename)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Thumbnail not found locally")
        
        with open(file_path, "rb") as f:
            content = f.read()
        return Response(content=content, media_type="image/png")
