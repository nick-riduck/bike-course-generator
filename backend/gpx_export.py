from __future__ import annotations
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import List, Dict, Any
import math

RIDUCK_NS = 'https://riduck.dev/xmlns/1'
ET.register_namespace('riduck', RIDUCK_NS)

INTERNAL_TO_GPX_SYM = {
    'turn_left': 'Turn Left',
    'turn_right': 'Turn Right',
    'straight': 'Straight',
    'u_turn': 'U-Turn',
    'food': 'Restaurant',
    'water': 'Drinking Water',
    'summit': 'Summit',
    'danger': 'Danger',
    'info': 'Information',
}

INTERNAL_TO_TCX_MAP = {
    'turn_left': 'Left',
    'turn_right': 'Right',
    'straight': 'Straight',
    'food': 'Food',
    'water': 'Water',
    'summit': 'Summit',
    'danger': 'Danger',
    'info': 'Generic',
    'via': 'Generic',
    'section_start': 'Generic',
    'u_turn': 'Generic',
}

class GpxExporter:
    def __init__(self, data: Dict[str, Any]):
        """
        data: Riduck Standard JSON format (specifically requiring 'editor_state')
        """
        self.data = data
        self.sections = data.get('editor_state', {}).get('sections', [])
        # If editor_state is missing but 'sections' is at root (frontend payload might vary), handle it
        if not self.sections and 'sections' in data:
            self.sections = data['sections']

    def to_xml_string(self) -> str:
        # Namespace map
        ns_map = {
            "xmlns": "http://www.topografix.com/GPX/1/1",
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:schemaLocation": "http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd",
            f"xmlns:riduck": RIDUCK_NS,
            "version": "1.1",
            "creator": "Riduck"
        }

        gpx = ET.Element("gpx", ns_map)
        
        # Metadata
        metadata = ET.SubElement(gpx, "metadata")
        name = ET.SubElement(metadata, "name")
        first_section_name = self.sections[0].get('name', 'Riduck Route') if self.sections else 'Riduck Route'
        name.text = self.data.get('title', first_section_name)

        # 1. Waypoints (Sections & POIs)
        for s_idx, section in enumerate(self.sections):
            points = section.get('points', [])
            section_color = section.get('color', '#2a9e92')
            section_name = section.get('name', f'Section {s_idx + 1}')

            for p_idx, point in enumerate(points):
                # Ensure lat/lon are floats
                lat = str(point.get('lat', 0))
                lon = str(point.get('lng', 0)) # Frontend uses 'lng'
                
                wpt = ET.SubElement(gpx, "wpt", lat=lat, lon=lon)
                
                # Elevation if available
                if 'ele' in point:
                    ele = ET.SubElement(wpt, "ele")
                    ele.text = str(point['ele'])
                
                # dist_km
                dist_km = point.get('dist_km')
                dist_km_str = f"{float(dist_km):.6f}" if dist_km is not None else None

                # Section Start Logic (First point of section)
                if p_idx == 0:
                    n = ET.SubElement(wpt, "name")
                    n.text = section_name

                    desc = ET.SubElement(wpt, "desc")
                    desc.text = f"Color:{section_color}" + (f";Riduck_DistKm={dist_km_str}" if dist_km_str else "")

                    sym = ET.SubElement(wpt, "sym")
                    sym.text = "Riduck_Section_Start"
                else:
                    # Regular Point
                    p_name = point.get('name', '')
                    if p_name:
                        n = ET.SubElement(wpt, "name")
                        n.text = p_name

                    point_type = point.get('type', 'via')
                    desc_parts = []
                    if point_type and point_type != 'via':
                        desc_parts.append(f"Riduck_Type:{point_type}")
                        # Also set <sym> for external tool compatibility
                        gpx_sym = INTERNAL_TO_GPX_SYM.get(point_type)
                        if gpx_sym:
                            sym_el = ET.SubElement(wpt, "sym")
                            sym_el.text = gpx_sym
                    if dist_km_str:
                        desc_parts.append(f"Riduck_DistKm={dist_km_str}")
                    if desc_parts:
                        desc = ET.SubElement(wpt, "desc")
                        desc.text = ";".join(desc_parts)

                # extensions: riduck:dist_km (primary)
                if dist_km_str:
                    ext = ET.SubElement(wpt, "extensions")
                    dk = ET.SubElement(ext, f"{{{RIDUCK_NS}}}dist_km")
                    dk.text = dist_km_str

        # 2. Track (Merged)
        trk = ET.SubElement(gpx, "trk")
        trk_name = ET.SubElement(trk, "name")
        trk_name.text = self.data.get('title', 'Riduck Track')
        
        trkseg = ET.SubElement(trk, "trkseg")
        
        last_coord_key = None
        
        for section in self.sections:
            segments = section.get('segments', [])
            for segment in segments:
                coords = segment.get('geometry', {}).get('coordinates', [])
                # Coords format: [[lon, lat, ele?], ...]
                
                for coord in coords:
                    if len(coord) < 2: continue
                    
                    lon = float(coord[0])
                    lat = float(coord[1])
                    ele = float(coord[2]) if len(coord) > 2 else None
                    
                    # Deduplication key (simple string check)
                    coord_key = f"{lat:.6f},{lon:.6f}"
                    
                    if coord_key != last_coord_key:
                        trkpt = ET.SubElement(trkseg, "trkpt", lat=str(lat), lon=str(lon))
                        if ele is not None:
                            e = ET.SubElement(trkpt, "ele")
                            e.text = str(ele)
                        last_coord_key = coord_key

        # Pretty Print
        rough_string = ET.tostring(gpx, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ")

class TcxExporter:
    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.sections = data.get('editor_state', {}).get('sections', [])
        if not self.sections and 'sections' in data:
            self.sections = data['sections']

    def _haversine_distance(self, lat1, lon1, lat2, lon2) -> float:
        R = 6371000 
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    def to_xml_string(self) -> str:
        ns_url = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
        root = ET.Element("TrainingCenterDatabase", {"xmlns": ns_url})
        
        courses = ET.SubElement(root, "Courses")
        course = ET.SubElement(courses, "Course")
        
        # Course Name
        name_elem = ET.SubElement(course, "Name")
        title = self.data.get('title', 'Riduck Route')
        name_elem.text = title

        lap = ET.SubElement(course, "Lap")
        
        # Track
        track = ET.SubElement(course, "Track")
        
        total_distance = 0.0
        last_pt = None
        last_coord_key = None
        
        # Fake Start Time (Epoch or specific date)
        # Using a fixed date ensures reproducibility. 
        # 2026-02-20T10:00:00Z
        start_epoch = 1771581600 
        avg_speed_mps = 5.5 # ~20km/h

        def get_time_str(seconds_offset):
            import datetime
            dt = datetime.datetime.utcfromtimestamp(start_epoch + seconds_offset)
            return dt.strftime('%Y-%m-%dT%H:%M:%SZ')

        # 1. Track Points
        for section in self.sections:
            segments = section.get('segments', [])
            for segment in segments:
                coords = segment.get('geometry', {}).get('coordinates', [])
                
                for coord in coords:
                    if len(coord) < 2: continue
                    lon, lat = float(coord[0]), float(coord[1])
                    ele = float(coord[2]) if len(coord) > 2 else 0.0
                    
                    coord_key = f"{lat:.6f},{lon:.6f}"
                    if coord_key == last_coord_key: continue
                    last_coord_key = coord_key

                    if last_pt:
                        dist = self._haversine_distance(last_pt[0], last_pt[1], lat, lon)
                        total_distance += dist
                    
                    last_pt = (lat, lon)

                    tp = ET.SubElement(track, "Trackpoint")
                    
                    # Time (Required)
                    t_elem = ET.SubElement(tp, "Time")
                    t_elem.text = get_time_str(total_distance / avg_speed_mps)

                    pos = ET.SubElement(tp, "Position")
                    lat_deg = ET.SubElement(pos, "LatitudeDegrees")
                    lat_deg.text = f"{lat:.6f}"
                    lon_deg = ET.SubElement(pos, "LongitudeDegrees")
                    lon_deg.text = f"{lon:.6f}"
                    
                    alt = ET.SubElement(tp, "AltitudeMeters")
                    alt.text = f"{ele:.1f}"
                    
                    dist_m = ET.SubElement(tp, "DistanceMeters")
                    dist_m.text = f"{total_distance:.1f}"

        # Lap Totals
        total_time_seconds = total_distance / avg_speed_mps
        tot_time = ET.SubElement(lap, "TotalTimeSeconds")
        tot_time.text = f"{total_time_seconds:.1f}"
        dist_meters = ET.SubElement(lap, "DistanceMeters")
        dist_meters.text = f"{total_distance:.1f}"
        
        # 2. Course Points (Waypoints)
        # Re-calculate distance for mapping waypoints
        current_cumulative_dist = 0.0
        
        for s_idx, section in enumerate(self.sections):
            points = section.get('points', [])
            segments = section.get('segments', [])
            
            # The structure is usually: P0 --Seg0--> P1 --Seg1--> P2 ...
            # So Points[i] is at the START of Segments[i] (conceptually for distance calc)
            # Except the last point.
            
            # Note: Riduck's section model might share points. 
            # If we iterate strictly, we assume `points[i]` corresponds to the start of `segments[i]` 
            # and `points[i+1]` is the end of `segments[i]`.
            
            segment_idx = 0
            
            for p_idx, point in enumerate(points):
                # Determine if this point should be exported
                # We export:
                # 1. Section Start (p_idx == 0)
                # 2. Intermediate Points (Via)
                # 3. End point (if it's the very last point of the entire route)
                
                # Check if this point is the start of the NEXT section (shared point)
                is_last_in_section = (p_idx == len(points) - 1)
                is_last_section = (s_idx == len(self.sections) - 1)
                
                # If it's the last point of a section BUT NOT the last section, 
                # it will be the first point of the next section. Skip to avoid duplicate/confusion.
                if is_last_in_section and not is_last_section:
                    continue

                lat = float(point.get('lat', 0))
                lon = float(point.get('lng', 0))
                name = point.get('name', '')
                
                # dist_km
                dist_km = point.get('dist_km')
                dist_km_str = f"{float(dist_km):.6f}" if dist_km is not None else None

                # Determine Type & Notes
                point_type = point.get('type', 'via')
                pt_type = INTERNAL_TO_TCX_MAP.get(point_type, 'Generic')
                notes = ""

                if p_idx == 0:
                    # Section Start
                    name = section.get('name', name or f'Section {s_idx+1}')
                    color = section.get('color', '#2a9e92')
                    notes = f"Riduck_Section:Color={color}"
                    if point_type not in ('section_start', 'via'):
                        notes += f";Riduck_Type:{point_type}"
                    if dist_km_str:
                        notes += f";Riduck_DistKm={dist_km_str}"
                else:
                    # Intermediate Point
                    if not name: name = "Point"
                    notes_parts = []
                    if point_type not in ('via',):
                        notes_parts.append(f"Riduck_Type:{point_type}")
                    if dist_km_str:
                        notes_parts.append(f"Riduck_DistKm={dist_km_str}")
                    notes = ";".join(notes_parts)

                # Create Element
                cp = ET.SubElement(course, "CoursePoint")
                ET.SubElement(cp, "Name").text = str(name)
                ET.SubElement(cp, "Time").text = get_time_str(current_cumulative_dist / avg_speed_mps)

                pos = ET.SubElement(cp, "Position")
                ET.SubElement(pos, "LatitudeDegrees").text = f"{lat:.6f}"
                ET.SubElement(pos, "LongitudeDegrees").text = f"{lon:.6f}"

                ET.SubElement(cp, "PointType").text = pt_type
                if notes:
                    ET.SubElement(cp, "Notes").text = notes

                # extensions: riduck:dist_km (primary)
                if dist_km_str:
                    ext = ET.SubElement(cp, "Extensions")
                    dk = ET.SubElement(ext, f"{{{RIDUCK_NS}}}dist_km")
                    dk.text = dist_km_str

                # Advance distance for the NEXT point (which is at the end of current segment)
                if not is_last_in_section:
                    # Add distance of the segment following this point
                    if segment_idx < len(segments):
                        seg = segments[segment_idx]
                        coords = seg.get('geometry', {}).get('coordinates', [])
                        seg_dist = 0.0
                        for k in range(len(coords)-1):
                            seg_dist += self._haversine_distance(coords[k][1], coords[k][0], coords[k+1][1], coords[k+1][0])
                        current_cumulative_dist += seg_dist
                        segment_idx += 1

        # Pretty Print
        rough_string = ET.tostring(root, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ")
