import os
import sys

# Ensure the backend directory is in the path so we can import gpx_loader, etc.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sentry_sdk

sentry_sdk.init(
    dsn="https://93e723471fc93415696de14850f21982@o4511017491169280.ingest.us.sentry.io/4511017595961344",
    traces_sample_rate=1.0,
    send_default_pii=True,
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.routers import auth, routes, thumbnails, export, plan, waypoints

app = FastAPI(title="Bike Course Generator API")

# Static files (waypoint images, thumbnails, etc.)
storage_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage")
if os.path.exists(storage_dir):
    app.mount("/storage", StaticFiles(directory=storage_dir), name="storage")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth.router)
app.include_router(routes.router)
app.include_router(thumbnails.router)
app.include_router(export.router)
app.include_router(plan.router)
app.include_router(waypoints.router)

@app.get("/")
async def root():
    return {"message": "Bike Course Generator API is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
