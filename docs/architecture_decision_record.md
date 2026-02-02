# Architecture Decision Record (ADR) - 2026-01-30

## 1. Routing Engine Migration (Project Valhalla)

### Decision
Migrate from **OpenRouteService (ORS)** to **Valhalla**.

### Context & Rationale
*   **Initial Constraint:** Previous decision to use ORS was based on "South Korea only" scope.
*   **New Requirement:** Target market expanded to include **Greater China (China + Taiwan)** and Global.
*   **Critical Issue (Memory & Cost):** 
    *   ORS loads the entire graph into RAM. China's map data (1.3GB PBF) requires 64GB+ RAM to run multiple profiles (Road, MTB, etc.), leading to excessive cloud costs ($200+/month).
    *   **Valhalla** uses a **Tiled Hierarchical Structure**, allowing it to run efficiently on low-memory instances (e.g., 8GB RAM) by loading only necessary tiles.
*   **Dynamic Costing:** Valhalla supports dynamic costing (grade avoidance, bike type) at request time without rebuilding graphs.

### Implementation Status
*   **Docker Image:** `ghcr.io/gis-ops/docker-valhalla:latest` (Official & Community standard)
*   **Data Sources:** South Korea + China (Geofabrik PBFs)
*   **Features Enabled:** Elevation (Skadi), Admin Areas, Time Zones.

---

## 2. Backend Architecture

### Decision
Implement a **Middleware Backend** using **Python (FastAPI)**.

### Architecture Diagram
```mermaid
graph LR
    User[Frontend (React/Vite)] -- HTTP --> Backend[FastAPI Server]
    Backend -- HTTP (JSON) --> Valhalla[Valhalla Docker (Port 8002)]
    Valhalla -- JSON --> Backend
    Backend -- Enhanced GeoJSON --> User
```

### Key Responsibilities (Backend)
1.  **Proxy & Security:** Hides the internal Valhalla API and manages CORS/Authentication in the future.
2.  **Data Transformation (BFF Pattern):** 
    *   Receives raw path data from Valhalla.
    *   **Processes Surface/Waytype:** Parses edge attributes and splits the route into colored segments (e.g., Paved=Blue, Unpaved=Orange).
    *   **Returns "Ready-to-Render" GeoJSON:** Frontend simply renders the provided features without complex mapping logic.
3.  **GPX Support:** 
    *   Provides `full_geometry` (LineString) separately for GPX file generation and elevation charts.

### Technology Stack
*   **Language:** Python 3.12+
*   **Framework:** FastAPI (Async/Await support, Auto-docs)
*   **Libraries:** `httpx` (Async HTTP), `sqlalchemy` (Future DB support), `pydantic` (Validation).

---

## 3. Data Response Strategy (Option 2 - Hybrid)

### Decision
The Backend will return a **Hybrid Response** containing both display-optimized data and raw data.

### JSON Structure
```json
{
  "summary": {
    "distance": 12.5, // km
    "ascent": 150,    // meters
    "time": 3600      // seconds
  },
  "display_geojson": { 
    // Optimization: Pre-colored segments for map rendering
    "type": "FeatureCollection",
    "features": [
      { 
        "geometry": { ... }, 
        "properties": { "color": "#2a9e92", "surface": "paved", "type": "road" } 
      },
      { 
        "geometry": { ... }, 
        "properties": { "color": "#FF9800", "surface": "gravel", "type": "offroad" } 
      }
    ]
  },
  "full_geometry": {
    // Optimization: Single continuous LineString for GPX export & Elevation Chart
    "type": "LineString",
    "coordinates": [[127.0, 37.0, 15], [127.01, 37.01, 18], ...] 
  }
}
```

### Benefits
*   **Frontend Simplicity:** Removes complex color mapping logic from the client.
*   **Consistency:** GPX export uses `full_geometry` ensuring a continuous track, while the map displays detailed segment information.
*   **Flexibility:** Design changes (e.g., changing "gravel" color) can be deployed via the Backend without updating the Frontend app.

---

## 4. Deployment Strategy

### Current (Development/MVP)
*   **Host:** Single VM (or Local Machine) via Docker Compose.
*   **Components:** Frontend (Vite), Backend (FastAPI), Valhalla (Engine) all on the same network.
*   **Reason:** Cost-effective and zero-latency communication between Backend and Valhalla.

### Future (Production)
*   **Valhalla:** Dedicated High-Memory VM (optimized for I/O).
*   **Backend:** Can be migrated to **Serverless (AWS Lambda / GCP Cloud Run)** easily due to stateless architecture.
*   **Frontend:** Static hosting (S3/CloudFront or Vercel).
