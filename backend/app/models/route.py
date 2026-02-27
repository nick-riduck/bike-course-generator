from pydantic import BaseModel
from typing import List, Optional
from app.models.common import Location

class RouteCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    status: Optional[str] = "PUBLIC"
    tags: Optional[List[str]] = []
    is_overwrite: Optional[bool] = False
    route_id: Optional[int] = None
    parent_route_id: Optional[int] = None
    summary_path: Optional[List[Location]] = None
    distance: Optional[int] = 0
    elevation_gain: Optional[int] = 0
    data_file_path: Optional[str] = ""
    full_data: Optional[dict] = None
    editor_state: Optional[dict] = None

class GpxExportRequest(BaseModel):
    title: str
    editor_state: dict
    format: Optional[str] = "gpx" # "gpx" or "tcx"

class RouteRequest(BaseModel):
    locations: List[Location]
    bicycle_type: Optional[str] = "Road"
    use_hills: Optional[float] = 0.5
    use_roads: Optional[float] = 0.5
