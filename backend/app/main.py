import os
import sys

# Ensure the backend directory is in the path so we can import gpx_loader, etc.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, routes, thumbnails, export, plan

app = FastAPI(title="Bike Course Generator API")

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

@app.get("/")
async def root():
    return {"message": "Bike Course Generator API is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
