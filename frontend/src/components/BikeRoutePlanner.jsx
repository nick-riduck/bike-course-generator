import React, { useState, useCallback, useRef, useMemo } from 'react';
import { Map, Source, Layer, Marker, Popup } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import ElevationChart from './ElevationChart';
import SidebarNav from './SidebarNav';
import MenuPanel from './MenuPanel';
import SearchPanel from './SearchPanel';

const INITIAL_VIEW_STATE = {
  longitude: 126.978,
  latitude: 37.566,
  zoom: 12
};

const generateId = () => Math.random().toString(36).substr(2, 9);

const SECTION_COLORS = ['#2a9e92', '#4CAF50', '#FF9800', '#E91E63', '#9C27B0', '#3F51B5'];

const generateGPX = (sections) => {
  const flatSegments = sections.flatMap(s => s.segments);
  if (flatSegments.length === 0) return null;
  const header = `<?xml version="1.0" encoding="UTF-8"?><gpx version="1.1" creator="Riduck" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>`;
  const footer = `</trkseg></trk></gpx>`;
  let trkpts = '';
  flatSegments.forEach(seg => {
    const coords = seg.geometry?.coordinates || [];
    coords.forEach(coord => {
      trkpts += `<trkpt lat="${coord[1]}" lon="${coord[0]}">${coord[2] !== undefined ? `<ele>${coord[2]}</ele>` : ''}</trkpt>`;
    });
  });
  return header + trkpts + footer;
};

const BikeRoutePlanner = () => {
  const mapRef = useRef();
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  
  // 지하철/철도 라인 켜기
  const handleMapLoad = (e) => {
    const map = e.target;
    try {
      const layers = map.getStyle().layers;
      layers.forEach(layer => {
        if (layer.id.includes('subway') || layer.id.includes('railway') || layer.id.includes('transit')) {
          map.setLayoutProperty(layer.id, 'visibility', 'visible');
        }
      });
    } catch (err) {
      console.log("Layer styling warning:", err);
    }
  };

  const [sections, setSections] = useState([
    { id: generateId(), name: 'Section 1', points: [], segments: [], color: SECTION_COLORS[0] }
  ]);
  const [isMockMode, setIsMockMode] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingMsg, setLoadingMsg] = useState('');
  const [hoveredCoord, setHoveredCoord] = useState(null);
  const [history, setHistory] = useState({ past: [], future: [] });
  const [hoverInfo, setHoverInfo] = useState(null);
  const [insertCandidate, setInsertCandidate] = useState(null);
  const [dragState, setDragState] = useState(null); // { candidate, lng, lat }
  const dragStateRef = useRef(null);
  const [hoveredSectionIndex, setHoveredSectionIndex] = useState(null);
  const [ambiguityPopup, setAmbiguityPopup] = useState(null);

  const handleHoverPoint = useCallback((coord) => setHoveredCoord(coord), []);

  const handleSectionHover = useCallback((index) => {
    setHoveredSectionIndex(index);
  }, []);

  const onHover = useCallback(event => {
    const { features, point: { x, y }, lngLat } = event;
    const hoveredFeature = features && features[0];
    
    // 1. Surface Info Tooltip
    if (hoveredFeature && hoveredFeature.properties.surface) {
        setHoverInfo({ feature: hoveredFeature, x, y });
    } else {
        setHoverInfo(null);
    }

    // 2. Insert Candidate Detection (On Line Hover) & Drag Handling
    if (dragStateRef.current) {
        // Dragging: Update drag position
        const newDragState = { ...dragStateRef.current, lng: lngLat.lng, lat: lngLat.lat };
        setDragState(newDragState);
        dragStateRef.current = newDragState;
        return;
    }

    if (hoveredFeature && hoveredFeature.layer.id === 'route-layer') {
        const secIdx = hoveredFeature.properties.sectionIndex;
        const segIdx = hoveredFeature.properties.segmentIndex;

        if (secIdx !== undefined && segIdx !== undefined) {
            setInsertCandidate({
                lng: lngLat.lng,
                lat: lngLat.lat,
                sectionIdx: secIdx,
                segmentIdx: segIdx
            });
            return;
        }
    }
    setInsertCandidate(null);
  }, [dragState]);

  const performInsertPoint = async (candidate, lng, lat) => {
      if (!candidate) return;
      setAmbiguityPopup(null);
      const { sectionIdx, segmentIdx } = candidate;
      const newPointId = generateId();
      const newPoint = { id: newPointId, lng, lat, type: 'via', name: '' };

      saveToHistory(sections);
      
      const updatedSections = [...sections];
      const targetSection = { ...updatedSections[sectionIdx] };
      const targetSegment = targetSection.segments[segmentIdx];
      
      // Find insertion index in points array
      const endPointIndex = targetSection.points.findIndex(p => p.id === targetSegment.endPointId);
      
      if (endPointIndex === -1) return;

      // Insert point
      const newPoints = [...targetSection.points];
      newPoints.splice(endPointIndex, 0, newPoint);
      targetSection.points = newPoints;

      // Update Segments
      const prevPoint = newPoints[endPointIndex - 1];
      const nextPoint = newPoints[endPointIndex + 1];
      
      const seg1Id = generateId();
      const seg2Id = generateId();
      
      const newSeg1 = { 
          id: seg1Id, startPointId: prevPoint.id, endPointId: newPointId, 
          geometry: { type: 'LineString', coordinates: [[prevPoint.lng, prevPoint.lat], [lng, lat]] }, 
          distance: 0, ascent: 0, type: 'loading' 
      };
      const newSeg2 = { 
          id: seg2Id, startPointId: newPointId, endPointId: nextPoint.id, 
          geometry: { type: 'LineString', coordinates: [[lng, lat], [nextPoint.lng, nextPoint.lat]] }, 
          distance: 0, ascent: 0, type: 'loading' 
      };

      const newSegments = [...targetSection.segments];
      newSegments.splice(segmentIdx, 1, newSeg1, newSeg2);
      targetSection.segments = newSegments;
      
      updatedSections[sectionIdx] = targetSection;
      setSections(updatedSections);
      setInsertCandidate(null);

      // Fetch Routes
      setIsLoading(true);
      try {
          const [res1, res2] = await Promise.all([
              fetchSegmentData(prevPoint, newPoint, isMockMode ? 'mock' : 'real'),
              fetchSegmentData(newPoint, nextPoint, isMockMode ? 'mock' : 'real')
          ]);

          setSections(prev => {
              const latest = [...prev];
              const sec = { ...latest[sectionIdx] };
              
              sec.segments = sec.segments.map(s => {
                  if (s.id === seg1Id) return res1 ? { ...s, ...res1 } : { ...s, type: 'error' };
                  if (s.id === seg2Id) return res2 ? { ...s, ...res2 } : { ...s, type: 'error' };
                  return s;
              });
              
              latest[sectionIdx] = sec;
              return latest;
          });
      } finally {
          setIsLoading(false);
          setLoadingMsg('');
      }
  };

  const handleUndo = () => {
    if (history.past.length === 0) return;
    const prev = history.past[history.past.length - 1];
    setHistory(curr => ({ 
      past: curr.past.slice(0, -1), 
      future: [JSON.parse(JSON.stringify(sections)), ...curr.future] 
    }));
    setSections(prev);
  };

  const handleRedo = () => {
    if (history.future.length === 0) return;
    const next = history.future[0];
    setHistory(curr => ({ 
      past: [...curr.past, JSON.parse(JSON.stringify(sections))], 
      future: curr.future.slice(1) 
    }));
    setSections(next);
  };

  const saveToHistory = (currentSections) => {
    setHistory(curr => ({ 
      past: [...curr.past, JSON.parse(JSON.stringify(currentSections))], 
      future: [] 
    }));
  };

  const fetchSegmentData = async (start, end, mode) => {
    if (mode === 'mock') {
        return { 
            geometry: { type: 'LineString', coordinates: [[start.lng, start.lat], [end.lng, end.lat]] }, 
            distance: 0, ascent: 0, type: 'mock', surfaceSegments: [] 
        };
    }
    setLoadingMsg('Finding Route...');
    try {
      const response = await fetch(`/api/route_v2`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            locations: [{lat: start.lat, lon: start.lng}, {lat: end.lat, lon: end.lng}],
            bicycle_type: "Road",
            use_hills: 0.5,
            use_roads: 0.5
          })
      });
      if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          if (response.status === 400 && errorData.detail) alert(errorData.detail);
          else throw new Error(`Backend error: ${response.status}`);
          return null;
      }
      const data = await response.json();
      const rawFeatures = data.display_geojson.features || [];
      const cleanFeatures = rawFeatures.map(f => ({
          type: 'Feature',
          geometry: { type: 'LineString', coordinates: f.geometry.coordinates },
          properties: {
              color: f.properties.color || '#2a9e92',
              surface: f.properties.surface || 'unknown',
              description: f.properties.description || ''
          }
      }));
      return { 
        geometry: data.full_geometry, 
        distance: data.summary.distance, 
        ascent: data.summary.ascent, 
        type: 'api', 
        surfaceSegments: cleanFeatures
      };
    } catch (e) { 
      console.error(e); 
      return { 
          geometry: { type: 'LineString', coordinates: [[start.lng, start.lat], [end.lng, end.lat]] }, 
          distance: 0, ascent: 0, type: 'error', surfaceSegments: [] 
      };
    } finally { setIsLoading(false); setLoadingMsg(''); }
  };

  const handleDragStart = (e) => {
      if (insertCandidate) {
          e.preventDefault(); // Prevent map pan
          // Deep clone candidate to avoid reference issues
          const candidateClone = { ...insertCandidate };
          const newDragState = { candidate: candidateClone, lng: insertCandidate.lng, lat: insertCandidate.lat };
          setDragState(newDragState);
          dragStateRef.current = newDragState;
          setInsertCandidate(null); // Hide hover marker
      }
  };

  const handleDragEnd = useCallback((e) => {
    if (dragStateRef.current) {
        const { candidate, lng, lat } = dragStateRef.current;
        if (candidate && candidate.sectionIdx !== undefined) {
            performInsertPoint(candidate, lng, lat);
        }
        setDragState(null);
        dragStateRef.current = null;
    }
  }, [performInsertPoint]);

  // Attach global mouseup listener when dragging
  React.useEffect(() => {
    // Only attach/detach when dragging starts/ends (not on every move)
    if (dragState) {
      window.addEventListener('mouseup', handleDragEnd);
      return () => window.removeEventListener('mouseup', handleDragEnd);
    }
  }, [!!dragState, handleDragEnd]);

  const handleMapClick = async (e) => {
    if (e.originalEvent.target.closest('.mapboxgl-marker')) return;
    
    // If we were dragging, click might fire? Usually drag prevents click.
    // But just in case.
    if (dragState) return;

    // Normal Click: Always Append to End
    const { lng, lat } = e.lngLat;
    const newPoint = { id: generateId(), lng, lat, type: 'via', name: '' };
    
    saveToHistory(sections);

    const updatedSections = [...sections];
    let activeSectionIndex = updatedSections.length - 1;

    // Safeguard: If no sections exist, create a new one
    if (activeSectionIndex < 0) {
        updatedSections.push({ 
            id: generateId(), 
            name: 'Section 1', 
            points: [], 
            segments: [], 
            color: SECTION_COLORS[0] 
        });
        activeSectionIndex = 0;
    }

    const activeSection = { ...updatedSections[activeSectionIndex] };
    const newPoints = [...activeSection.points, newPoint];
    activeSection.points = newPoints;
    updatedSections[activeSectionIndex] = activeSection;
    
    setSections(updatedSections);
    
    if (newPoints.length > 1) {
      const lastPoint = newPoints[newPoints.length - 2];
      const segmentId = generateId();
      const loadingSegment = { 
          id: segmentId, startPointId: lastPoint.id, endPointId: newPoint.id, 
          geometry: { type: 'LineString', coordinates: [[lastPoint.lng, lastPoint.lat], [newPoint.lng, newPoint.lat]] }, 
          distance: 0, ascent: 0, type: 'loading' 
      };
      
      activeSection.segments = [...activeSection.segments, loadingSegment];
      setSections([...updatedSections]);

      setIsLoading(true);
      try {
          const realData = await fetchSegmentData(lastPoint, newPoint, isMockMode ? 'mock' : 'real');
          if (realData) {
              activeSection.segments = activeSection.segments.map(s => s.id === segmentId ? { ...s, ...realData } : s);
          } else {
              activeSection.segments = activeSection.segments.filter(s => s.id !== segmentId);
              activeSection.points = activeSection.points.slice(0, -1);
          }
          setSections([...updatedSections]);
      } catch(e) { }
    }
  };

  const handlePointRemove = async (sectionIdx, pointIdx, e) => {
    e?.stopPropagation();
    saveToHistory(sections);
    
    let updatedSections = JSON.parse(JSON.stringify(sections)); // Deep copy to avoid mutation issues
    const targetSection = updatedSections[sectionIdx];
    const targetPoint = targetSection.points[pointIdx];
    
    // 1. Remove Point from current section
    const prevPointInSec = targetSection.points[pointIdx - 1];
    const nextPointInSec = targetSection.points[pointIdx + 1];

    // Remove segments connected to this point
    targetSection.segments = targetSection.segments.filter(s => 
        s.startPointId !== targetPoint.id && s.endPointId !== targetPoint.id
    );
    // Remove the point itself
    targetSection.points.splice(pointIdx, 1);

    // 2. Handle Reconnection within Section
    let segmentsToFetch = [];
    
    if (prevPointInSec && nextPointInSec) {
        // Was middle point: Reconnect Prev -> Next
        const segmentId = generateId();
        const loadingSeg = { 
            id: segmentId, startPointId: prevPointInSec.id, endPointId: nextPointInSec.id, 
            geometry: { type: 'LineString', coordinates: [[prevPointInSec.lng, prevPointInSec.lat], [nextPointInSec.lng, nextPointInSec.lat]] }, 
            distance: 0, ascent: 0, type: 'loading' 
        };
        targetSection.segments.push(loadingSeg);
        // Ensure segments are sorted? For now array push is fine as we filter/map.
        // Actually, order matters for rendering if we want continuous line in list, but map renders features independently.
        segmentsToFetch.push({ sectionIdx, segmentId, start: prevPointInSec, end: nextPointInSec });
    }

    // 3. Handle Section Boundary (If Head or Tail was removed)
    
    // A. If Head Removed (pointIdx === 0)
    if (pointIdx === 0 && sectionIdx > 0) {
        // Need to update previous section's last segment to point to NEW head (which is targetSection.points[0])
        const prevSection = updatedSections[sectionIdx - 1];
        const newHead = targetSection.points[0];
        
        if (newHead) {
            // Reconnect PrevSec.LastPoint -> NewHead
            const lastPointOfPrev = prevSection.points[prevSection.points.length - 1];
            const segmentId = generateId();
            const loadingSeg = {
                id: segmentId, startPointId: lastPointOfPrev.id, endPointId: newHead.id,
                geometry: { type: 'LineString', coordinates: [[lastPointOfPrev.lng, lastPointOfPrev.lat], [newHead.lng, newHead.lat]] },
                distance: 0, ascent: 0, type: 'loading'
            };
            
            // Remove old last segment of prev section
            // It was pointing to targetPoint.id
            prevSection.segments = prevSection.segments.filter(s => s.endPointId !== targetPoint.id);
            prevSection.segments.push(loadingSeg);
            
            segmentsToFetch.push({ sectionIdx: sectionIdx - 1, segmentId, start: lastPointOfPrev, end: newHead });
        }
    }
    
    // B. If Tail Removed
    // No special handling needed because next section's head is independent.
    // Wait, if I remove the Tail of Section 1, Section 2's Head is still there. 
    // But the link (S1's last segment) is gone.
    // If I remove P_last of S1, S1's new last point is P_last-1.
    // But S2 starts at P_next_head.
    // There is NO link between S1 and S2 anymore!
    // We must ADD a link from S1's NEW tail to S2's head.
    
    if (!nextPointInSec && sectionIdx < updatedSections.length - 1) {
        // Tail removed, and there is a next section
        const nextSection = updatedSections[sectionIdx + 1];
        const nextHead = nextSection.points[0];
        const newTail = targetSection.points[targetSection.points.length - 1]; // New tail
        
        if (newTail && nextHead) {
             const segmentId = generateId();
             const loadingSeg = {
                id: segmentId, startPointId: newTail.id, endPointId: nextHead.id,
                geometry: { type: 'LineString', coordinates: [[newTail.lng, newTail.lat], [nextHead.lng, nextHead.lat]] },
                distance: 0, ascent: 0, type: 'loading'
            };
            targetSection.segments.push(loadingSeg);
            segmentsToFetch.push({ sectionIdx, segmentId, start: newTail, end: nextHead });
        }
    }

    // 4. Auto-Cleanup: Remove Empty Sections
    if (targetSection.points.length === 0) {
        updatedSections.splice(sectionIdx, 1);
        
        // If we removed a section in the middle, we must bridge the gap
        if (sectionIdx > 0 && sectionIdx < updatedSections.length) { // length is now -1
             const prevSec = updatedSections[sectionIdx - 1];
             const nextSec = updatedSections[sectionIdx]; // was i+1
             
             const pStart = prevSec.points[prevSec.points.length - 1];
             const pEnd = nextSec.points[0];
             
             if (pStart && pEnd) {
                 const segmentId = generateId();
                 const loadingSeg = {
                    id: segmentId, startPointId: pStart.id, endPointId: pEnd.id,
                    geometry: { type: 'LineString', coordinates: [[pStart.lng, pStart.lat], [pEnd.lng, pEnd.lat]] },
                    distance: 0, ascent: 0, type: 'loading'
                };
                prevSec.segments.push(loadingSeg);
                segmentsToFetch.push({ sectionIdx: sectionIdx - 1, segmentId, start: pStart, end: pEnd });
             }
        }
    } else {
        updatedSections[sectionIdx] = targetSection;
    }

    setSections(updatedSections);

    if (segmentsToFetch.length > 0) {
        setIsLoading(true);
        try {
            await Promise.all(segmentsToFetch.map(async ({ sectionIdx: sIdx, segmentId, start, end }) => {
                const realData = await fetchSegmentData(start, end, isMockMode ? 'mock' : 'real');
                setSections(prev => {
                    const latest = JSON.parse(JSON.stringify(prev));
                    if (!latest[sIdx]) return prev; // Section might have been deleted? No, index should be valid.
                    const sec = latest[sIdx];
                    sec.segments = sec.segments.map(s => s.id === segmentId ? { ...s, ...realData } : s);
                    return latest;
                });
            }));
        } finally { setIsLoading(false); setLoadingMsg(''); }
    }
  };

  // Section Management Handlers
  const handleSectionDelete = async (sectionIdx) => {
      saveToHistory(sections);
      let updatedSections = JSON.parse(JSON.stringify(sections));
      const deletedSection = sections[sectionIdx];
      
      // Simply remove the section
      updatedSections.splice(sectionIdx, 1);
      
      // Bridge the gap or Cleanup
      let segmentsToFetch = [];
      if (sectionIdx > 0) {
          const prevSec = updatedSections[sectionIdx - 1];
          
          if (sectionIdx < updatedSections.length) {
              // Middle section deleted: Bridge Prev -> Next
              const nextSec = updatedSections[sectionIdx];
              const pStart = prevSec.points[prevSec.points.length - 1];
              const pEnd = nextSec.points[0];
              
              if (pStart && pEnd) {
                 const segmentId = generateId();
                 const loadingSeg = {
                    id: segmentId, startPointId: pStart.id, endPointId: pEnd.id,
                    geometry: { type: 'LineString', coordinates: [[pStart.lng, pStart.lat], [pEnd.lng, pEnd.lat]] },
                    distance: 0, ascent: 0, type: 'loading'
                };
                prevSec.segments.push(loadingSeg);
                segmentsToFetch.push({ sectionIdx: sectionIdx - 1, segmentId, start: pStart, end: pEnd });
              }
          } else {
              // Last section deleted: Remove the connecting segment from previous section
              // that was pointing to the deleted section's head.
              const headOfDeleted = deletedSection.points[0];
              if (headOfDeleted) {
                  prevSec.segments = prevSec.segments.filter(s => s.endPointId !== headOfDeleted.id);
              }
          }
      }
      
      setSections(updatedSections);
      
      if (segmentsToFetch.length > 0) {
        setIsLoading(true);
        try {
            await Promise.all(segmentsToFetch.map(async ({ sectionIdx: sIdx, segmentId, start, end }) => {
                const realData = await fetchSegmentData(start, end, isMockMode ? 'mock' : 'real');
                setSections(prev => {
                    const latest = JSON.parse(JSON.stringify(prev));
                    const sec = latest[sIdx];
                    sec.segments = sec.segments.map(s => s.id === segmentId ? { ...s, ...realData } : s);
                    return latest;
                });
            }));
        } finally { setIsLoading(false); setLoadingMsg(''); }
      }
  };

  const handleSectionMerge = (sectionIdx) => {
      // Merge with NEXT section
      if (sectionIdx >= sections.length - 1) return;
      saveToHistory(sections);
      
      let updatedSections = JSON.parse(JSON.stringify(sections));
      const currSec = updatedSections[sectionIdx];
      const nextSec = updatedSections[sectionIdx + 1];
      
      // Move points and segments from Next to Curr
      currSec.points = [...currSec.points, ...nextSec.points];
      currSec.segments = [...currSec.segments, ...nextSec.segments];
      
      // Remove Next Section
      updatedSections.splice(sectionIdx + 1, 1);
      
      // Note: The "Bridge" segment connecting currSec.last -> nextSec.first
      // should ALREADY exist in currSec.segments if logic is correct.
      // Because currSec is responsible for reaching nextSec.first.
      
      setSections(updatedSections);
  };

  const handleSectionRename = (sectionIdx, newName) => {
      const updatedSections = [...sections];
      updatedSections[sectionIdx].name = newName;
      setSections(updatedSections);
  };

  const handleSectionDownload = (sectionIdx) => {
      const gpx = generateGPX([sections[sectionIdx]]);
      if(gpx) { 
        const blob = new Blob([gpx], { type: 'application/gpx+xml' }); 
        const url = URL.createObjectURL(blob); 
        const a = document.createElement('a'); 
        a.href = url; a.download = `section-${sections[sectionIdx].name}-${Date.now()}.gpx`; a.click(); 
    }
  };

  const handlePointMove = async (sectionIdx, pointIdx, evt) => {
    const { lng, lat } = evt.lngLat;
    saveToHistory(sections);

    let updatedSections = JSON.parse(JSON.stringify(sections));
    const targetSection = updatedSections[sectionIdx];
    
    // Update Point Location
    const currPoint = targetSection.points[pointIdx];
    currPoint.lng = lng;
    currPoint.lat = lat;
    
    let segmentsToFetch = [];

    // 1. Current Section: Prev -> Curr
    const prevPoint = targetSection.points[pointIdx - 1];
    if (prevPoint) {
        const segId = generateId();
        const loadingSeg = {
            id: segId, startPointId: prevPoint.id, endPointId: currPoint.id,
            geometry: { type: 'LineString', coordinates: [[prevPoint.lng, prevPoint.lat], [lng, lat]] },
            distance: 0, ascent: 0, type: 'loading'
        };
        targetSection.segments = targetSection.segments.map(s => 
            (s.startPointId === prevPoint.id && s.endPointId === currPoint.id) ? loadingSeg : s
        );
        segmentsToFetch.push({ sectionIdx, segmentId: segId, start: prevPoint, end: currPoint });
    }

    // 2. Current Section: Curr -> Next
    const nextPoint = targetSection.points[pointIdx + 1];
    if (nextPoint) {
        const segId = generateId();
        const loadingSeg = {
            id: segId, startPointId: currPoint.id, endPointId: nextPoint.id,
            geometry: { type: 'LineString', coordinates: [[lng, lat], [nextPoint.lng, nextPoint.lat]] },
            distance: 0, ascent: 0, type: 'loading'
        };
        targetSection.segments = targetSection.segments.map(s => 
            (s.startPointId === currPoint.id && s.endPointId === nextPoint.id) ? loadingSeg : s
        );
        segmentsToFetch.push({ sectionIdx, segmentId: segId, start: currPoint, end: nextPoint });
    }

    // 3. SPECIAL: Previous Section's Last Segment (Leading into this Header)
    // If this point is the FIRST point of a section (and not the first section of all)
    if (pointIdx === 0 && sectionIdx > 0) {
        const prevSection = updatedSections[sectionIdx - 1];
        const lastPointOfPrevSection = prevSection.points[prevSection.points.length - 1];
        
        if (lastPointOfPrevSection) {
            const segId = generateId();
            const loadingSeg = {
                id: segId, startPointId: lastPointOfPrevSection.id, endPointId: currPoint.id,
                geometry: { type: 'LineString', coordinates: [[lastPointOfPrevSection.lng, lastPointOfPrevSection.lat], [lng, lat]] },
                distance: 0, ascent: 0, type: 'loading'
            };
            // Replace the segment that connects prevSection.last -> currentSection.first
            prevSection.segments = prevSection.segments.map(s => 
                s.endPointId === currPoint.id ? loadingSeg : s
            );
            segmentsToFetch.push({ sectionIdx: sectionIdx - 1, segmentId: segId, start: lastPointOfPrevSection, end: currPoint });
        }
    }

    setSections(updatedSections);

    if (segmentsToFetch.length > 0) {
        setIsLoading(true);
        try {
            await Promise.all(segmentsToFetch.map(async ({ sectionIdx: sIdx, segmentId, start, end }) => {
                const realData = await fetchSegmentData(start, end, isMockMode ? 'mock' : 'real');
                setSections(prev => {
                    const latest = JSON.parse(JSON.stringify(prev));
                    const sec = latest[sIdx];
                    sec.segments = sec.segments.map(s => s.id === segmentId ? { ...s, ...realData } : s);
                    return latest;
                });
            }));
        } finally { setIsLoading(false); setLoadingMsg(''); }
    }
  };

  const handleSplitSection = (sectionIdx, pointIdx) => {
    if (pointIdx <= 0 || pointIdx >= sections[sectionIdx].points.length) return;
    
    saveToHistory(sections);
    const updatedSections = JSON.parse(JSON.stringify(sections));
    const targetSection = updatedSections[sectionIdx];
    
    // P_new_1 (targetSection.points[pointIdx]) becomes the header of the new section
    const pointsBefore = targetSection.points.slice(0, pointIdx); 
    const pointsAfter = targetSection.points.slice(pointIdx); 
    
    // Segments leading to SplitPoint stay in targetSection
    const splitPointId = targetSection.points[pointIdx].id;
    const segmentsBefore = targetSection.segments.filter(seg => {
        // If endPoint is the split point or before it
        const endIdx = targetSection.points.findIndex(p => p.id === seg.endPointId);
        return endIdx !== -1 && endIdx <= pointIdx;
    });
    
    const segmentsAfter = targetSection.segments.filter(seg => {
        // If startPoint is the split point or after it
        const startIdx = targetSection.points.findIndex(p => p.id === seg.startPointId);
        return startIdx !== -1 && startIdx >= pointIdx;
    });

    const newSection = {
      id: generateId(),
      name: `Section ${updatedSections.length + 1}`,
      points: pointsAfter,
      segments: segmentsAfter,
      color: SECTION_COLORS[updatedSections.length % SECTION_COLORS.length]
    };

    targetSection.points = pointsBefore;
    targetSection.segments = segmentsBefore;
    updatedSections.splice(sectionIdx + 1, 0, newSection);
    setSections(updatedSections);
  };

  const totalDist = sections.reduce((acc, sec) => acc + sec.segments.reduce((sAcc, s) => sAcc + (s.distance || 0), 0), 0);
  const totalAscent = sections.reduce((acc, sec) => acc + sec.segments.reduce((sAcc, s) => sAcc + (s.ascent || 0), 0), 0);

  const surfaceGeoJSON = useMemo(() => ({
    type: 'FeatureCollection',
    features: sections.flatMap((sec, secIdx) => sec.segments.flatMap((s, segIdx) => {
        // Base Props
        const props = { 
            color: sec.color, // Default Section Color
            sectionIndex: secIdx, 
            segmentIndex: segIdx 
        };

        // Override color based on state
        if (s.type === 'mock') props.color = '#FFA726';
        else if (s.type === 'loading') props.color = '#9E9E9E';
        else if (s.type === 'error') props.color = '#F44336';
        
        // If hovered in menu, force section color highlight
        if (hoveredSectionIndex === secIdx) {
            props.color = sec.color; 
            // Maybe brighten or thicken? For now just color is fine.
        }

        if (s.surfaceSegments && s.surfaceSegments.length > 0) {
            return s.surfaceSegments.map(fs => {
                const finalProps = {
                    ...props, // 1. Base Props (Section Color)
                    ...fs.properties, // 2. Surface Props (Override with Surface Color e.g. Green/Brown)
                    sectionColor: sec.color // Keep original section color for reference
                };

                // 3. Force Section Color if Hovered (Highest Priority)
                if (hoveredSectionIndex === secIdx) {
                    finalProps.color = sec.color;
                }

                return { 
                    ...fs, 
                    properties: finalProps
                };
            });
        }
        return [{ type: 'Feature', geometry: s.geometry, properties: props }];
    }))
  }), [sections, hoveredSectionIndex]);

  const handleDownloadGPX = () => {
    const gpx = generateGPX(sections); 
    if(gpx) { 
        const blob = new Blob([gpx], { type: 'application/gpx+xml' }); 
        const url = URL.createObjectURL(blob); 
        const a = document.createElement('a'); 
        a.href = url; a.download = `route-${Date.now()}.gpx`; a.click(); 
    }
  };

  const handleSaveRoute = () => {
      // TODO: Implement Save Logic
      alert("Save functionality coming soon!");
  };

  // Toggle handlers for SidebarNav
  const toggleMenu = () => {
    setIsMenuOpen(prev => !prev);
  };

  const toggleSearch = () => {
    setIsSearchOpen(prev => !prev);
  };

  return (
    <div className="flex w-full h-full relative overflow-hidden">
      {/* 1. Left Sidebar Navigation (Toolbar) */}
      <SidebarNav 
        isMenuOpen={isMenuOpen} 
        isSearchOpen={isSearchOpen} 
        onToggleMenu={toggleMenu} 
        onToggleSearch={toggleSearch} 
      />

      {/* 2. Panels Container (Stackable) */}
      <div className="flex shrink-0 h-full relative z-40">
        {/* Menu Panel */}
        <div className={`
            ${isMenuOpen ? 'w-80 border-r border-gray-800' : 'w-0'} 
            h-full bg-gray-900 overflow-hidden transition-all duration-300 ease-in-out
        `}>
            <div className="w-80 h-full"> {/* Inner Fixed Width Container */}
                <MenuPanel 
                    history={history}
                    onUndo={handleUndo}
                    onRedo={handleRedo}
                    onClear={() => { saveToHistory(sections); setSections([{ id: generateId(), name: 'Section 1', points: [], segments: [], color: SECTION_COLORS[0] }]); }}
                    onSave={handleSaveRoute}
                    onDownloadGPX={handleDownloadGPX}
                    sections={sections}
                    onPointRemove={handlePointRemove}
                    onSplitSection={handleSplitSection}
                    onSectionHover={handleSectionHover}
                    onSectionDelete={handleSectionDelete}
                    onSectionMerge={handleSectionMerge}
                    onSectionRename={handleSectionRename}
                    onSectionDownload={handleSectionDownload}
                    isMockMode={isMockMode}
                    setIsMockMode={setIsMockMode}
                />
            </div>
        </div>

        {/* Search Panel */}
        <div className={`
            ${isSearchOpen ? 'w-80 border-r border-gray-800' : 'w-0'} 
            h-full bg-gray-900 overflow-hidden transition-all duration-300 ease-in-out
        `}>
             <div className="w-80 h-full"> {/* Inner Fixed Width Container */}
                <SearchPanel />
             </div>
        </div>
      </div>

      {/* 3. Main Content (Right) - Map & Chart */}
      <div className="flex-1 flex flex-col relative h-full min-w-0">
        {isLoading && <div className="absolute inset-0 z-[9999] bg-black/30 backdrop-blur-[2px] flex flex-col items-center justify-center"><div className="animate-spin rounded-full h-12 w-12 border-b-4 border-riduck-primary mb-4"></div><div className="text-white font-bold text-lg animate-pulse">{loadingMsg}</div></div>}
        
        {/* Map Area */}
        <div className="flex-1 relative">
            {/* Stats Overlay */}
            <div className="absolute top-6 left-1/2 transform -translate-x-1/2 z-10 bg-gray-900/90 backdrop-blur-md px-8 py-3 rounded-full border border-gray-700 shadow-2xl flex gap-8 items-center pointer-events-none">
                <div className="text-center">
                    <p className="text-[10px] text-gray-400 uppercase font-bold tracking-wider">Distance</p>
                    <p className="text-2xl font-mono text-white font-bold">{totalDist.toFixed(1)}<span className="text-sm text-gray-500 ml-1">km</span></p>
                </div>
                <div className="w-px h-8 bg-gray-700"></div>
                <div className="text-center">
                    <p className="text-[10px] text-gray-400 uppercase font-bold tracking-wider">Ascent</p>
                    <p className="text-2xl font-mono text-white font-bold">{Math.round(totalAscent)}<span className="text-sm text-gray-500 ml-1">m</span></p>
                </div>
            </div>

            <Map 
                ref={mapRef} 
                initialViewState={INITIAL_VIEW_STATE} 
                mapStyle="https://api.maptiler.com/maps/jp-mierune-dark/style.json?key=hmAnzLL30c4tItQZZ8B9" 
                onLoad={handleMapLoad}
                onClick={handleMapClick}
                onMouseMove={onHover}
                
                onMouseLeave={() => { setHoverInfo(null); setDragState(null); }} // Cancel drag if leave?
                interactiveLayerIds={['route-layer']}
                style={{ width: '100%', height: '100%' }} 
                cursor={isLoading ? 'wait' : (dragState ? 'grabbing' : (insertCandidate ? 'grab' : 'crosshair'))}
            >
                {surfaceGeoJSON.features.length > 0 && (
                    <Source id="route-source" type="geojson" data={surfaceGeoJSON}>
                        <Layer id="route-layer" type="line" layout={{ 'line-join': 'round', 'line-cap': 'round' }} paint={{ 'line-color': ['get', 'color'], 'line-width': 6, 'line-opacity': 0.9 }} />
                    </Source>
                )}
                
                {/* Drag Preview Line */}
                {dragState && dragState.candidate && (() => {
                     const sec = sections[dragState.candidate.sectionIdx];
                     if (!sec) return null;
                     const segment = sec.segments[dragState.candidate.segmentIdx];
                     if (!segment) return null;
                     const startP = sec.points.find(p => p.id === segment.startPointId);
                     const endP = sec.points.find(p => p.id === segment.endPointId);
                     if (!startP || !endP) return null;

                     const previewGeoJson = {
                         type: 'Feature',
                         geometry: {
                             type: 'LineString',
                             coordinates: [
                                 [startP.lng, startP.lat],
                                 [dragState.lng, dragState.lat],
                                 [endP.lng, endP.lat]
                             ]
                         }
                     };

                     return (
                         <Source id="drag-preview" type="geojson" data={previewGeoJson}>
                             <Layer 
                                 id="drag-preview-layer" 
                                 type="line" 
                                 paint={{ 
                                     'line-color': '#FFFFFF', 
                                     'line-width': 4, 
                                     'line-dasharray': [2, 2],
                                     'line-opacity': 0.8 
                                 }} 
                             />
                         </Source>
                     );
                })()}

                {/* Virtual Handle (Hover) */}
                {insertCandidate && !dragState && (
                    <Marker
                        longitude={insertCandidate.lng}
                        latitude={insertCandidate.lat}
                        anchor="center"
                        draggable={false} // We handle drag manually via map events
                    >
                        <div 
                            className="w-4 h-4 bg-white rounded-full shadow-md border-2 border-gray-800 cursor-grab hover:scale-125 transition-transform"
                            onMouseDown={(e) => {
                                e.stopPropagation(); // Prevent map click
                                handleDragStart(e);
                            }}
                        ></div>
                    </Marker>
                )}

                {/* Drag Handle (Active) */}
                {dragState && (
                    <Marker
                        longitude={dragState.lng}
                        latitude={dragState.lat}
                        anchor="center"
                        draggable={false}
                    >
                        <div className="w-5 h-5 bg-riduck-primary rounded-full shadow-lg border-2 border-white cursor-grabbing"></div>
                    </Marker>
                )}

                {sections.flatMap((sec, sIdx) => sec.points.map((p, pIdx, arr) => (
                    <Marker 
                        key={`${sec.id}-${p.id}`} 
                        longitude={p.lng} 
                        latitude={p.lat} 
                        anchor="center"
                        draggable={true}
                        onDragEnd={(evt) => handlePointMove(sIdx, pIdx, evt)}
                    >
                    <div 
                      className={`group flex items-center justify-center w-6 h-6 rounded-full border-2 border-white shadow-lg cursor-pointer text-white text-xs font-black z-50 hover:scale-110 transition-transform`} 
                      style={{ backgroundColor: sIdx === 0 && pIdx === 0 ? '#10B981' : (sIdx === sections.length - 1 && pIdx === arr.length - 1 ? '#EF4444' : sec.color) }}
                      onClick={(e) => handlePointRemove(sIdx, pIdx, e)}
                    >
                        <span className="group-hover:hidden">{pIdx + 1}</span><span className="hidden group-hover:block">✕</span>
                    </div>
                    </Marker>
                )))}
                {ambiguityPopup && (
                    <Popup
                        longitude={ambiguityPopup.lng}
                        latitude={ambiguityPopup.lat}
                        anchor="bottom"
                        onClose={() => setAmbiguityPopup(null)}
                        closeButton={true}
                        closeOnClick={false}
                        maxWidth="300px"
                    >
                        <div className="p-2 bg-gray-900 text-white rounded-lg">
                            <p className="text-[10px] font-black uppercase tracking-widest text-gray-500 mb-2 px-1">Select Section to Insert</p>
                            <div className="flex flex-col gap-1.5">
                                {ambiguityPopup.candidates.map((cand, idx) => (
                                    <button
                                        key={idx}
                                        className="flex items-center gap-3 w-full p-2.5 rounded-xl bg-gray-800 hover:bg-riduck-primary transition-all text-left group"
                                        onClick={() => performInsertPoint(cand, ambiguityPopup.lng, ambiguityPopup.lat)}
                                    >
                                        <div className="w-3 h-3 rounded-full shrink-0 shadow-sm" style={{ backgroundColor: sections[cand.sectionIdx]?.color }}></div>
                                        <div className="flex-1 min-w-0">
                                            <p className="text-xs font-bold truncate">{sections[cand.sectionIdx]?.name || `Section ${cand.sectionIdx + 1}`}</p>
                                            <p className="text-[9px] text-gray-400 group-hover:text-white/80">Segment #{cand.segmentIdx + 1}</p>
                                        </div>
                                    </button>
                                ))}
                            </div>
                        </div>
                    </Popup>
                )}
                {hoverInfo && (
                    <div className="absolute z-50 pointer-events-none bg-gray-900/95 text-white p-3 rounded-lg text-xs border border-gray-600 shadow-xl backdrop-blur-md" style={{left: hoverInfo.x + 15, top: hoverInfo.y + 15}}>
                        <div className="flex items-center gap-2 mb-1">
                            <div className="w-3 h-3 rounded-full shadow-sm" style={{backgroundColor: hoverInfo.feature.properties.color}}></div>
                            <span className="font-bold text-sm">{hoverInfo.feature.properties.surface}</span>
                        </div>
                        {hoverInfo.feature.properties.description && (
                            <div className="mt-1 text-[11px] text-gray-400 leading-tight max-w-[200px]">
                                {hoverInfo.feature.properties.description}
                            </div>
                        )}
                    </div>
                )}
            </Map>
        </div>

        {/* Elevation Chart (Bottom Fixed with Padding) */}
        <div className="h-40 md:h-52 border-t border-gray-800 bg-gray-900/90 backdrop-blur-md relative z-10 px-4 pb-6 pt-2 shrink-0">
            <ElevationChart segments={sections.flatMap(s => s.segments)} onHoverPoint={handleHoverPoint} />
        </div>
      </div>
    </div>
  );
};

export default BikeRoutePlanner;