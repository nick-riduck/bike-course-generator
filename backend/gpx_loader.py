from __future__ import annotations

import re
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

@dataclass
class TrackPoint:
    lat: float
    lon: float
    ele: float
    distance_from_start: float = 0.0

class BaseTrackLoader:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.points: List[TrackPoint] = []
        self.parsed_waypoints: List[Dict[str, Any]] = []

    def load(self):
        raise NotImplementedError

    def process_with_valhalla(self, valhalla_client) -> Dict[str, Any]:
        """
        Uses Valhalla to analyze the track (surface, elevation) and snaps waypoints.
        Returns the final JSON structure for the frontend.
        """
        if not self.points:
            raise ValueError("No track points loaded.")

        # 1. Valhalla Analysis
        shape_points = [{"lat": p.lat, "lon": p.lon} for p in self.points]
        standard_data = valhalla_client.get_standard_course(shape_points)
        
        v_lats = standard_data['points']['lat']
        v_lons = standard_data['points']['lon']
        v_eles = standard_data['points']['ele']
        
        # 2. Snap Waypoints to Valhalla Track
        updated_waypoints = []
        if self.parsed_waypoints:
            for wpt in self.parsed_waypoints:
                min_dist = float('inf')
                best_idx = 0
                for i in range(len(v_lats)):
                    d = (wpt['lat'] - v_lats[i])**2 + (wpt['lon'] - v_lons[i])**2
                    if d < min_dist:
                        min_dist = d
                        best_idx = i
                
                wpt_copy = wpt.copy()
                wpt_copy['index'] = best_idx
                wpt_copy['lat'] = v_lats[best_idx]
                wpt_copy['lon'] = v_lons[best_idx]
                updated_waypoints.append(wpt_copy)
            
            updated_waypoints.sort(key=lambda x: x['index'])

        # 3. Ensure Start/End Waypoints Exist
        if v_lats:
            last_idx = len(v_lats) - 1
            
            # Check Start (Allow small tolerance of 5 points)
            if not updated_waypoints or updated_waypoints[0]['index'] > 5:
                updated_waypoints.insert(0, {
                    "lat": v_lats[0], "lon": v_lons[0], 
                    "name": "Start", "sym": "Flag, Green", "color": "#4CAF50", 
                    "type": "section_start", "index": 0
                })
            
            # Check End
            if not updated_waypoints or updated_waypoints[-1]['index'] < last_idx - 5:
                updated_waypoints.append({
                    "lat": v_lats[last_idx], "lon": v_lons[last_idx], 
                    "name": "End", "sym": "Flag, Red", "color": "#F44336", 
                    "type": "via", "index": last_idx
                })

        # 4. Build Features (Surface Info)
        features = []
        segs = standard_data['segments']
        surface_info = {
            1: ("Asphalt", "Smooth paved road.", "#2979FF"),
            2: ("Concrete", "Concrete surface.", "#2979FF"),
            3: ("Special", "Wood or metal surface. Caution!", "#9E9E9E"),
            4: ("Paving Stones", "Paving stones or cobblestones.", "#FFC400"),
            5: ("Cycleway", "Dedicated bicycle path.", "#00E676"),
            6: ("Compacted", "Compacted fine gravel.", "#8D6E63"),
            7: ("Unpaved", "Gravel or dirt road. Rough terrain.", "#8D6E63"),
            0: ("Unknown", "Unknown surface type.", "#9E9E9E")
        }
        
        for i in range(len(segs['p_start'])):
            s_idx = segs['p_start'][i]
            e_idx = segs['p_end'][i]
            surf_id = segs['surf_id'][i]
            label, description, color = surface_info.get(surf_id, surface_info[0])
            
            seg_coords = [[v_lons[k], v_lats[k]] for k in range(s_idx, e_idx + 1)]
            if len(seg_coords) >= 2:
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": seg_coords},
                    "properties": {
                        "color": color, 
                        "surface": label, 
                        "description": description,
                        "start_index": s_idx,
                        "end_index": e_idx
                    }
                })

        return {
            "summary": {
                "distance": standard_data['stats']['distance'] / 1000.0,
                "ascent": standard_data['stats']['ascent']
            },
            "full_geometry": {
                "type": "LineString",
                "coordinates": [[float(v_lons[i]), float(v_lats[i]), float(v_eles[i])] for i in range(len(v_lats))]
            },
            "display_geojson": {"type": "FeatureCollection", "features": features},
            "waypoints": updated_waypoints
        }

    def _haversine_distance(self, lat1, lon1, lat2, lon2) -> float:
        R = 6371000 
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

class GpxLoader(BaseTrackLoader):
    def __init__(self, gpx_path: str):
        super().__init__(gpx_path)

    def load(self):
        """Parses the GPX file to extract raw track points and waypoints."""
        tree = ET.parse(self.file_path)
        root = tree.getroot()
        
        # Handle Namespace
        ns_url = 'http://www.topografix.com/GPX/1/1'
        ns = {'gpx': ns_url}
        if '}' in root.tag and ns_url not in root.tag:
             ns_url = root.tag.split('}')[0].strip('{')
             ns = {'gpx': ns_url}

        # 1. Parse Track Points
        trkpts = root.findall(".//gpx:trkpt", ns) or root.findall(".//trkpt")
        self.points = []
        total_dist = 0.0
        prev_pt = None

        for pt in trkpts:
            lat = float(pt.attrib['lat'])
            lon = float(pt.attrib['lon'])
            
            ele_node = pt.find('gpx:ele', ns) or pt.find('ele')
            ele = float(ele_node.text) if ele_node is not None and ele_node.text else 0.0

            current_pt = TrackPoint(lat, lon, ele)
            if prev_pt:
                d = self._haversine_distance(prev_pt.lat, prev_pt.lon, current_pt.lat, current_pt.lon)
                if d < 0.5: continue
                total_dist += d
            
            current_pt.distance_from_start = total_dist
            self.points.append(current_pt)
            prev_pt = current_pt
            
        # 2. Parse Waypoints
        wpts = root.findall(".//gpx:wpt", ns) or root.findall(".//wpt")
        self.parsed_waypoints = []
        
        def get_text(node, tag_names):
            for tag in tag_names:
                child = node.find(tag, ns) if ':' in tag else node.find(tag)
                if child is not None and child.text:
                    return child.text
            return ""

        RIDUCK_NS = 'https://riduck.dev/xmlns/1'

        for wpt in wpts:
            lat = float(wpt.attrib['lat'])
            lon = float(wpt.attrib['lon'])

            name = get_text(wpt, ['gpx:name', 'name'])
            sym = get_text(wpt, ['gpx:sym', 'sym'])
            desc = get_text(wpt, ['gpx:desc', 'desc'])

            color = "#2a9e92"
            if "Riduck" in sym:
                color_match = re.search(r"Color:(#[0-9a-fA-F]{6})", desc)
                if color_match: color = color_match.group(1)

            # dist_km: extensions 우선, desc fallback
            dist_km = None
            ext_node = wpt.find(f'gpx:extensions', ns) or wpt.find('extensions')
            if ext_node is not None:
                dk_node = ext_node.find(f'{{{RIDUCK_NS}}}dist_km')
                if dk_node is not None and dk_node.text:
                    try: dist_km = float(dk_node.text)
                    except ValueError: pass
            if dist_km is None:
                dk_match = re.search(r"Riduck_DistKm=([\d.]+)", desc)
                if dk_match:
                    try: dist_km = float(dk_match.group(1))
                    except ValueError: pass

            self.parsed_waypoints.append({
                "lat": lat, "lon": lon, "name": name, "sym": sym, "color": color,
                "type": "section_start" if "Riduck_Section_Start" in sym else "via",
                "dist_km": dist_km
            })

class TcxLoader(BaseTrackLoader):
    def __init__(self, tcx_path: str):
        super().__init__(tcx_path)

    def load(self):
        """Parses the TCX file to extract raw track points and course points."""
        tree = ET.parse(self.file_path)
        root = tree.getroot()
        
        self.points = []
        self.parsed_waypoints = []
        
        total_dist = 0.0
        prev_pt = None

        # Helper to find child by local name (ignoring namespace)
        def find_child(parent, local_name):
            for child in parent:
                if child.tag.endswith(local_name):
                    return child
            return None

        # 1. Parse Track Points (Namespace Agnostic)
        for elem in root.iter():
            if elem.tag.endswith('Trackpoint'):
                tp = elem
                
                position = find_child(tp, 'Position')
                if position is None: continue
                
                lat_node = find_child(position, 'LatitudeDegrees')
                lon_node = find_child(position, 'LongitudeDegrees')
                
                if lat_node is None or lon_node is None: continue
                
                try:
                    lat = float(lat_node.text)
                    lon = float(lon_node.text)
                except (ValueError, AttributeError):
                    continue
                
                alt_node = find_child(tp, 'AltitudeMeters')
                ele = 0.0
                if alt_node is not None and alt_node.text:
                    try:
                        ele = float(alt_node.text)
                    except ValueError:
                        pass

                current_pt = TrackPoint(lat, lon, ele)
                
                if prev_pt:
                    d = self._haversine_distance(prev_pt.lat, prev_pt.lon, current_pt.lat, current_pt.lon)
                    if d < 0.5: continue
                    total_dist += d
                
                current_pt.distance_from_start = total_dist
                self.points.append(current_pt)
                prev_pt = current_pt

        # 2. Parse CoursePoints (Waypoints)
        for elem in root.iter():
            if elem.tag.endswith('CoursePoint'):
                cp = elem
                
                name_node = find_child(cp, 'Name')
                name = name_node.text if name_node is not None else "Point"
                
                notes_node = find_child(cp, 'Notes')
                notes = notes_node.text if notes_node is not None else ""
                
                pt_type_node = find_child(cp, 'PointType')
                pt_type = pt_type_node.text if pt_type_node is not None else "Generic"
                
                position = find_child(cp, 'Position')
                if position is None: continue
                
                lat_node = find_child(position, 'LatitudeDegrees')
                lon_node = find_child(position, 'LongitudeDegrees')
                
                if lat_node is None or lon_node is None: continue
                
                try:
                    lat = float(lat_node.text)
                    lon = float(lon_node.text)
                except (ValueError, AttributeError):
                    continue
                
                # Riduck Specific Parsing from Notes
                color = "#2a9e92"
                is_section_start = False

                if notes and "Riduck_Section" in notes:
                    is_section_start = True
                    color_match = re.search(r"Color:(#[0-9a-fA-F]{6})", notes)
                    if color_match: color = color_match.group(1)

                # dist_km: Extensions 우선, Notes fallback
                RIDUCK_NS = 'https://riduck.dev/xmlns/1'
                dist_km = None
                ext_node = find_child(cp, 'Extensions')
                if ext_node is not None:
                    for child in ext_node:
                        if child.tag.endswith('}dist_km') or child.tag == 'dist_km':
                            try: dist_km = float(child.text)
                            except (ValueError, TypeError): pass
                if dist_km is None and notes:
                    dk_match = re.search(r"Riduck_DistKm=([\d.]+)", notes)
                    if dk_match:
                        try: dist_km = float(dk_match.group(1))
                        except ValueError: pass

                self.parsed_waypoints.append({
                    "lat": lat, "lon": lon, "name": name, "sym": pt_type, "color": color,
                    "type": "section_start" if is_section_start else "via",
                    "dist_km": dist_km
                })

