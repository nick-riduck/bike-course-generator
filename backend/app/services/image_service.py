import io
from PIL import Image, ImageDraw
from typing import List
from app.core.storage import save_to_storage
from app.models.common import Location

def generate_thumbnail(locations: List[Location], route_uuid: str):
    if not locations: return None
    
    # 1. Calculate Bounding Box from FULL data
    lats_all = [loc.lat for loc in locations]
    lons_all = [loc.lon for loc in locations]
    min_lat, max_lat = min(lats_all), max(lats_all)
    min_lon, max_lon = min(lons_all), max(lons_all)
    
    # 2. Downsample for drawing
    step = max(1, len(locations) // 500)
    sampled = locations[::step]
    if len(sampled) > 0 and sampled[-1] != locations[-1]:
        sampled.append(locations[-1])
    
    # 3. Setup Image (Ratio ~2.5:1 to match UI)
    W, H = 600, 240
    padding = 40 
    img = Image.new('RGB', (W, H), color='#111827')
    draw = ImageDraw.Draw(img)
    
    # 4. Calculate Range and Scale
    lat_range = max_lat - min_lat
    lon_range = max_lon - min_lon
    
    if lat_range < 0.00001: lat_range = 0.0001
    if lon_range < 0.00001: lon_range = 0.0001
    
    # Fit inside (W-2*padding, H-2*padding)
    scale_x = (W - 2 * padding) / lon_range
    scale_y = (H - 2 * padding) / lat_range
    scale = min(scale_x, scale_y)
    
    # Centering offsets
    off_x = (W - lon_range * scale) / 2
    off_y = (H - lat_range * scale) / 2
    
    # 5. Transform Points
    points = []
    for loc in sampled:
        x = off_x + (loc.lon - min_lon) * scale
        y = off_y + (max_lat - loc.lat) * scale # Flip Y (max_lat is top)
        points.append((x, y))
        
    # 6. Draw
    if len(points) > 1:
        draw.line(points, fill='#2a9e92', width=5, joint='curve')
        
        # Start/End Markers
        r = 5
        # Start (Green)
        sx, sy = points[0]
        draw.ellipse((sx-r, sy-r, sx+r, sy+r), fill='#10B981', outline='white', width=1)
        # End (Red)
        ex, ey = points[-1]
        draw.ellipse((ex-r, ey-r, ex+r, ey+r), fill='#EF4444', outline='white', width=1)

    # 7. Save
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_bytes = img_byte_arr.getvalue()
    
    save_to_storage(img_bytes, "thumbnails", f"{route_uuid}.png")
    return f"/api/thumbnails/{route_uuid}.png"
