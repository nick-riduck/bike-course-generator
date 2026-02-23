from __future__ import annotations
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import List, Dict, Any

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
                
                # Section Start Logic (First point of section)
                if p_idx == 0:
                    n = ET.SubElement(wpt, "name")
                    n.text = section_name
                    
                    desc = ET.SubElement(wpt, "desc")
                    desc.text = f"Color:{section_color}"
                    
                    sym = ET.SubElement(wpt, "sym")
                    sym.text = "Riduck_Section_Start"
                else:
                    # Regular Point (Via)
                    p_name = point.get('name', '')
                    if p_name:
                        n = ET.SubElement(wpt, "name")
                        n.text = p_name

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
