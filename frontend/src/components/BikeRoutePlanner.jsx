import React, { useState, useCallback, useRef, useMemo } from 'react';
import { Map, Source, Layer, Marker, Popup } from 'react-map-gl/maplibre';
import { useAuth } from '../AuthContext';
import { auth } from '../firebase';
import 'maplibre-gl/dist/maplibre-gl.css';
import ElevationChart from './ElevationChart';
import SidebarNav from './SidebarNav';
import MenuPanel from './MenuPanel';
import SearchPanel from './SearchPanel';
import SaveRouteModal from './SaveRouteModal';
import ExportRouteModal from './ExportRouteModal';

const INITIAL_VIEW_STATE = {
  longitude: 126.978,
  latitude: 37.566,
  zoom: 12
};

const generateId = () => Math.random().toString(36).substr(2, 9);

const SECTION_COLORS = ['#2a9e92', '#4CAF50', '#FF9800', '#E91E63', '#9C27B0', '#3F51B5'];

const getDistance = (lat1, lon1, lat2, lon2) => {
    const R = 6371; // Radius of the earth in km
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = 
        Math.sin(dLat/2) * Math.sin(dLat/2) +
        Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * 
        Math.sin(dLon/2) * Math.sin(dLon/2); 
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a)); 
    return R * c; // Distance in km
};

const getProjectedDistance = (segmentCoords, targetLng, targetLat) => {
    // Handle potential nested coordinates (MultiLineString vs LineString)
    // Flatten if necessary, but usually segments are simple LineStrings [ [lon, lat], ... ]
    if (!segmentCoords || !Array.isArray(segmentCoords) || segmentCoords.length < 2) return 0;
    
    // Check if first element is number (invalid) or array (valid point)
    if (typeof segmentCoords[0] === 'number') return 0; 

    let minDistance = Infinity;
    let accumulatedDistance = 0;
    let closestPointDistance = 0;

    for (let i = 0; i < segmentCoords.length - 1; i++) {
        const pt1 = segmentCoords[i];
        const pt2 = segmentCoords[i+1];
        
        // Ensure points are arrays [lon, lat]
        if (!Array.isArray(pt1) || !Array.isArray(pt2)) continue;
        
        const [lon1, lat1] = pt1;
        const [lon2, lat2] = pt2;
        
        const segLen = getDistance(lat1, lon1, lat2, lon2);
        
        // Simple projection onto line segment (approximation)
        // Find t (0 to 1) that minimizes distance from point to line segment
        // Or just check distance to start and end points for simplicity if segLen is small
        // For better UX, let's just find the closest vertex index and use its accumulated distance.
        // Or better: Projection.
        
        // Let's use simple vertex matching for now as segments are usually dense.
        // Or simple projection:
        const x = targetLng, y = targetLat;
        const x1 = lon1, y1 = lat1;
        const x2 = lon2, y2 = lat2;
        
        const A = x - x1;
        const B = y - y1;
        const C = x2 - x1;
        const D = y2 - y1;
        
        const dot = A * C + B * D;
        const lenSq = C * C + D * D;
        let param = -1;
        if (lenSq !== 0) param = dot / lenSq;
        
        let xx, yy;
        let portion = 0; // 0 to 1 of this segment
        
        if (param < 0) {
            xx = x1; yy = y1;
            portion = 0;
        } else if (param > 1) {
            xx = x2; yy = y2;
            portion = 1;
        } else {
            xx = x1 + param * C;
            yy = y1 + param * D;
            portion = param;
        }
        
        const distToLine = getDistance(targetLat, targetLng, yy, xx);
        
        if (distToLine < minDistance) {
            minDistance = distToLine;
            closestPointDistance = accumulatedDistance + (segLen * portion);
        }
        
        accumulatedDistance += segLen;
    }
    return closestPointDistance;
};

const BikeRoutePlanner = ({ routeName, setRouteName, initialRouteId }) => {
  const { user, loginWithGoogle } = useAuth();
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
  const [isDirty, setIsDirty] = useState(false); // Track unsaved map changes

  // Route Metadata (Received via props)
  const [routeDescription, setRouteDescription] = useState('');
  const [routeStatus, setRouteStatus] = useState('PUBLIC');
  const [routeTags, setRouteTags] = useState([]);
  const [currentRouteId, setCurrentRouteId] = useState(null);
  const [routeStats, setRouteStats] = useState({ views: 0, downloads: 0 });
  const [routeOwnerId, setRouteOwnerId] = useState(null);
  const [isSaveModalOpen, setIsSaveModalOpen] = useState(false);
  const [isExportModalOpen, setIsExportModalOpen] = useState(false);

  // Preview State
  const [previewRoute, setPreviewRoute] = useState(null);

  // Place Search State
  const [isPlaceSearchOpen, setIsPlaceSearchOpen] = useState(false);
  const [placeSearchQuery, setPlaceSearchQuery] = useState('');

  // Long Press State for Mobile
  const longPressTimerRef = useRef(null);
  const isLongPressRef = useRef(false);
  const touchStartPosRef = useRef(null);

  // Animation Ref
  const animationRef = useRef(null);
  const previewInvalidLoggedRef = useRef(false);
  const dragPreviewInvalidLoggedRef = useRef(false);

  const handleHoverPoint = useCallback((coord) => setHoveredCoord(coord), []);

  const handleOpenExportModal = () => {
    if (!sections || sections.length === 0) return;
    setIsExportModalOpen(true);
  };

  const handlePreviewRoute = async (routeId) => {
    setIsLoading(true);
    setLoadingMsg('Loading Preview...');
    
    // Mobile UX: Close sidebar immediately to show map
    if (window.innerWidth < 768) {
        setIsSearchOpen(false);
        setIsMenuOpen(false);
    }

    try {
        const headers = {};
        if (auth.currentUser) {
            const idToken = await auth.currentUser.getIdToken();
            headers['Authorization'] = `Bearer ${idToken}`;
        }
        const res = await fetch(`/api/routes/${routeId}`, { headers });
        if (!res.ok) throw new Error("Failed to load route data");
        const data = await res.json();
        
        if (data.editor_state && data.editor_state.sections) {
             setPreviewRoute({
                 id: data.route_id,
                 data: data,
                 sections: data.editor_state.sections
             });
             // Fit map to preview sections
             fitMapToSections(data.editor_state.sections);
        } else {
             alert("Invalid route data for editor.");
        }
    } catch (e) {
        console.error(e);
        alert(`Error loading preview: ${e.message}`);
    } finally {
        setIsLoading(false);
        setLoadingMsg('');
    }
  };

  const confirmPreviewLoad = () => {
     if (!previewRoute) return;
     
     // Check for unsaved changes
     if (sections.some(s => s.points.length > 0)) {
          if (!confirm("Current route will be discarded. Load this route?")) return;
     }

     const { data } = previewRoute;
     
     setSections(data.editor_state.sections);
     setCurrentRouteId(data.route_id);
     setRouteName(data.title || '');
     setRouteDescription(data.description || '');
     setRouteStatus(data.status || 'PUBLIC');
     setRouteTags(data.tags || []);
     setRouteOwnerId(data.owner_id);
     setRouteStats(data.stats || { views: 0, downloads: 0 });
     
     setHistory({ past: [], future: [] });
     setIsDirty(false);
     
     // Close panels
     setIsMenuOpen(false);
     setIsSearchOpen(false);
     
     // Clear preview
     setPreviewRoute(null);
  };

  const cancelPreview = (options = {}) => {
      const { reopenSearchOnMobile = true } = options;
      setPreviewRoute(null);
      // Optionally fly back to current sections
      if (sections.some(s => s.points.length > 0)) {
          fitMapToSections(sections);
      }
      if (reopenSearchOnMobile && window.innerWidth < 768) {
          setIsSearchOpen(true);
      }
  };

  const performExport = async (filename, format) => {
    if (!sections || sections.length === 0) return;

    try {
        // Deep clone sections to remove any potential non-serializable properties
        const cleanSections = sections.map(sec => ({
            id: sec.id,
            name: sec.name,
            color: sec.color,
            points: sec.points.map(p => ({
                id: p.id,
                lat: p.lat,
                lng: p.lng,
                type: p.type,
                name: p.name
            })),
            segments: sec.segments.map(s => ({
                id: s.id,
                startPointId: s.startPointId,
                endPointId: s.endPointId,
                geometry: s.geometry,
                distance: s.distance,
                ascent: s.ascent,
                type: s.type
            }))
        }));

        const payload = {
            title: filename || routeName || 'Riduck Route',
            editor_state: {
                sections: cleanSections
            },
            format: format
        };

        const response = await fetch('/api/export/gpx', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || `Failed to generate ${format.toUpperCase()}`);
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        
        const contentDisposition = response.headers.get('Content-Disposition');
        let downloadFilename = `route-${Date.now()}.${format}`;
        if (contentDisposition) {
            const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
            if (filenameMatch && filenameMatch.length === 2)
                downloadFilename = filenameMatch[1];
        } else {
             const safeName = (filename || 'route').replace(/[^a-z0-9]/gi, '_').toLowerCase();
             downloadFilename = `${safeName}.${format}`;
        }

        const a = document.createElement('a');
        a.href = url;
        a.download = downloadFilename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        if (currentRouteId) {
            fetch(`/api/routes/${currentRouteId}/download`, { method: 'POST' }).catch(e => {});
        }

    } catch (e) {
        console.error(`${format.toUpperCase()} Export Error:`, e);
        alert(`Failed to download ${format.toUpperCase()}: ${e.message}`);
    }
  };

  const handleSectionDownload = async (sectionIdx, format = 'gpx') => {
    const section = sections[sectionIdx];
    if (!section) return;

    try {
        const payload = {
            title: section.name || 'Riduck Section',
            editor_state: {
                sections: [section] // Send only the specific section
            },
            format: format
        };

        const response = await fetch('/api/export/gpx', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to generate Section GPX');
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = `section-${section.name || 'Export'}-${Date.now()}.gpx`;
        if (contentDisposition) {
            const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
            if (filenameMatch && filenameMatch.length === 2)
                filename = filenameMatch[1];
        }

        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

    } catch (e) {
        console.error("Section GPX Export Error:", e);
        alert(`Failed to download Section GPX: ${e.message}`);
    }
  };

  const handleTouchStart = (e) => {
      // Only single touch
      if (e.points.length !== 1) return;
      
      const { x, y } = e.point;
      const { lng, lat } = e.lngLat;
      
      touchStartPosRef.current = { x, y };
      isLongPressRef.current = false;

      longPressTimerRef.current = setTimeout(() => {
          // Long Press Triggered
          isLongPressRef.current = true;
          
          // Check if we are on the route
          // We need to access the map instance directly or pass it via refs, 
          // but mapRef.current is available.
          if (!mapRef.current) return;
          
          const map = mapRef.current; // mapRef.current is the MapRef object
          const features = map.queryRenderedFeatures([x, y], { layers: ['route-layer'] });

          if (features.length > 0) {
              // Haptic feedback if available
              if (navigator.vibrate) navigator.vibrate(50);
              
              // Find insert candidate logic (reused from hover logic partially)
              // Since we don't have hover state, we calculate candidate now.
              const feature = features[0];
              const sectionIdx = feature.properties.sectionIndex;
              const segmentIdx = feature.properties.segmentIndex;
              
              if (sectionIdx !== undefined && segmentIdx !== undefined) {
                   const candidate = {
                       sectionIdx,
                       segmentIdx,
                       candidates: [{ sectionIdx, segmentIdx }] // simplified
                   };
                   performInsertPoint(candidate, lng, lat);
              }
          }
      }, 500); // 500ms threshold
  };

  const handleTouchMove = (e) => {
      if (!touchStartPosRef.current) return;
      const { x, y } = e.point;
      const dx = Math.abs(x - touchStartPosRef.current.x);
      const dy = Math.abs(y - touchStartPosRef.current.y);
      
      // If moved more than 10px, cancel long press (it's a drag/pan)
      if (dx > 10 || dy > 10) {
          clearTimeout(longPressTimerRef.current);
          touchStartPosRef.current = null;
      }
  };

  const handleTouchEnd = () => {
      clearTimeout(longPressTimerRef.current);
      touchStartPosRef.current = null;
      // Note: We don't prevent default click here. 
      // If long press fired, the point is inserted. 
      // If not, it's a tap, handled by onClick.
  };

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

    const routeFeatures = features ? features.filter(f => f.layer.id === 'route-layer') : [];

    if (routeFeatures.length > 0) {
        const candidates = routeFeatures.map(f => ({
            sectionIdx: f.properties.sectionIndex,
            segmentIdx: f.properties.segmentIndex
        })).filter(c => c.sectionIdx !== undefined && c.segmentIdx !== undefined);

        if (candidates.length > 0) {
            // Deduplicate if needed, but typically distinct segments
            setInsertCandidate({
                lng: lngLat.lng,
                lat: lngLat.lat,
                candidates: candidates,
                // Primary candidate (top-most)
                sectionIdx: candidates[0].sectionIdx,
                segmentIdx: candidates[0].segmentIdx
            });
            return;
        }
    }
    setInsertCandidate(null);
  }, []);

  const performInsertPoint = async (candidate, lng, lat) => {
      // Handle candidate object structure difference (direct vs via popup)
      const sectionIdx = candidate.sectionIdx ?? candidate.sectionIndex;
      const segmentIdx = candidate.segmentIdx ?? candidate.segmentIndex;

      if (sectionIdx === undefined || segmentIdx === undefined) return;

      setAmbiguityPopup(null);
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
    setIsDirty(true);
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
      alert(`Route Error: ${e.message || 'Failed to connect to route server.'}`);
      return { 
          geometry: { type: 'LineString', coordinates: [[start.lng, start.lat], [end.lng, end.lat]] }, 
          distance: 0, ascent: 0, type: 'error', surfaceSegments: [] 
      };
    }
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

  const getEnrichedCandidateInfo = useCallback((sectionIdx, segmentIdx, clickLng, clickLat) => {
      const section = sections[sectionIdx];
      if (!section) return null;

      const segment = section.segments[segmentIdx];
      if (!segment) return null;

      const startPoint = section.points.find(p => p.id === segment.startPointId);
      const endPoint = section.points.find(p => p.id === segment.endPointId);
      
      // Calculate accumulated distance up to this segment start
      let startDist = 0;
      for (let i = 0; i < sectionIdx; i++) {
          startDist += sections[i].segments.reduce((acc, s) => acc + (s.distance || 0), 0);
      }
      for (let j = 0; j < segmentIdx; j++) {
          startDist += section.segments[j].distance || 0;
      }
      
      // Calculate partial distance within segment
      const partialDist = getProjectedDistance(segment.geometry?.coordinates, clickLng, clickLat);
      const totalDist = startDist + partialDist;
      
      // Improve names: use index if name is empty
      const sIdx = section.points.findIndex(p => p.id === segment.startPointId);
      const eIdx = section.points.findIndex(p => p.id === segment.endPointId);
      
      const sName = startPoint?.name ? startPoint.name : `Point ${sIdx + 1}`;
      const eName = endPoint?.name ? endPoint.name : `Point ${eIdx + 1}`;

      return {
          sectionName: section.name,
          startPointName: sName,
          endPointName: eName,
          totalDistance: totalDist,
          sectionIdx,
          segmentIdx,
          sectionColor: section.color
      };
  }, [sections]);

  const handleDragEnd = useCallback((e) => {
    if (dragStateRef.current) {
        const { candidate, lng, lat } = dragStateRef.current;
        
        if (candidate) {
            if (candidate.candidates && candidate.candidates.length > 1) {
                // Enrich candidates with readable info & Sort by distance
                const enrichedCandidates = candidate.candidates.map(c => 
                    getEnrichedCandidateInfo(c.sectionIdx, c.segmentIdx, lng, lat)
                ).filter(c => c !== null).sort((a, b) => a.totalDistance - b.totalDistance);

                setAmbiguityPopup({
                    lng: lng,
                    lat: lat,
                    candidates: enrichedCandidates
                });
            } else if (candidate.sectionIdx !== undefined) {
                performInsertPoint(candidate, lng, lat);
            }
        }
        
        setDragState(null);
        dragStateRef.current = null;
    }
  }, [performInsertPoint, getEnrichedCandidateInfo]);

  // Attach global mouseup listener when dragging
  React.useEffect(() => {
    // Only attach/detach when dragging starts/ends (not on every move)
    if (dragState) {
      window.addEventListener('mouseup', handleDragEnd);
      return () => window.removeEventListener('mouseup', handleDragEnd);
    }
  }, [!!dragState, handleDragEnd]);

  const handleMapClick = async (e) => {
    if (previewRoute) {
        cancelPreview({ reopenSearchOnMobile: false });
        return;
    }

    // If panels are open on mobile, close them and do nothing else
    if (window.innerWidth < 768 && (isMenuOpen || isSearchOpen)) {
        setIsMenuOpen(false);
        setIsSearchOpen(false);
        return;
    }

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

      if (!isMockMode) {
          setIsLoading(true);
          setLoadingMsg('Finding Route...');
      }

      try {
          const realData = await fetchSegmentData(lastPoint, newPoint, isMockMode ? 'mock' : 'real');
          if (realData) {
              activeSection.segments = activeSection.segments.map(s => s.id === segmentId ? { ...s, ...realData } : s);
          } else {
              activeSection.segments = activeSection.segments.filter(s => s.id !== segmentId);
              activeSection.points = activeSection.points.slice(0, -1);
          }
          setSections([...updatedSections]);
      } catch(e) { 
          console.error(e);
      } finally {
          setIsLoading(false);
          setLoadingMsg('');
      }
    }
  };

  // Helper: Delete a section and manage connections
  const deleteSection = (sectionIdx, sectionsList) => {
      const segmentsToFetch = [];
      
      // 1. If there's a previous section, it likely has a "connector" segment 
      // pointing to the section being deleted. We MUST clean this up.
      if (sectionIdx > 0) {
          const prevSec = sectionsList[sectionIdx - 1];
          const prevPointsIds = new Set(prevSec.points.map(p => p.id));
          
          // A connector segment is one where endPointId is NOT in the section's own points.
          // We filter them out to sever the link to the deleted section.
          prevSec.segments = prevSec.segments.filter(s => prevPointsIds.has(s.endPointId));
          
          // 2. If there's a section AFTER the one being deleted, bridge the gap from Prev -> Next.
          if (sectionIdx < sectionsList.length - 1) {
              const nextSec = sectionsList[sectionIdx + 1];
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
      }

      // 3. Finally, remove the section from the list
      sectionsList.splice(sectionIdx, 1);
      
      return segmentsToFetch;
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
        segmentsToFetch.push({ sectionIdx, segmentId, start: prevPointInSec, end: nextPointInSec });
    }

    // 3. Handle Section Boundary (If Head or Tail was removed)
    
    // A. If Head Removed (pointIdx === 0)
    if (pointIdx === 0 && sectionIdx > 0) {
        const prevSection = updatedSections[sectionIdx - 1];
        const newHead = targetSection.points[0];
        
        if (newHead) {
            const lastPointOfPrev = prevSection.points[prevSection.points.length - 1];
            const segmentId = generateId();
            const loadingSeg = {
                id: segmentId, startPointId: lastPointOfPrev.id, endPointId: newHead.id,
                geometry: { type: 'LineString', coordinates: [[lastPointOfPrev.lng, lastPointOfPrev.lat], [newHead.lng, newHead.lat]] },
                distance: 0, ascent: 0, type: 'loading'
            };
            
            prevSection.segments = prevSection.segments.filter(s => s.endPointId !== targetPoint.id);
            prevSection.segments.push(loadingSeg);
            
            segmentsToFetch.push({ sectionIdx: sectionIdx - 1, segmentId, start: lastPointOfPrev, end: newHead });
        } else {
             // Section became empty, handled below
        }
    }
    
    // B. If Tail Removed
    if (!nextPointInSec && sectionIdx < updatedSections.length - 1) {
        const nextSection = updatedSections[sectionIdx + 1];
        const nextHead = nextSection.points[0];
        const newTail = targetSection.points[targetSection.points.length - 1]; 
        
        if (newTail && nextHead) {
             const segmentId = generateId();
             const loadingSeg = {
                id: segmentId, startPointId: newTail.id, endPointId: nextHead.id,
                geometry: { type: 'LineString', coordinates: [[newTail.lng, newTail.lat], [nextHead.lng, nextHead.lat]] },
                distance: 0, ascent: 0, type: 'loading'
            };
            targetSection.segments.push(loadingSeg);
            segmentsToFetch.push({ sectionIdx, segmentId, start: newTail, end: nextHead });
        } else {
             // Section became empty, handled below
        }
    }

    // 4. Auto-Cleanup: Remove Empty Sections
    if (targetSection.points.length === 0) {
        // Use shared logic!
        // We revert changes to `targetSection` in `updatedSections` (it's empty anyway)
        // and call deleteSection logic.
        // Actually, we modified `updatedSections` in place.
        // But `deleteSection` expects the list to HAVE the section at `sectionIdx`.
        // It currently DOES have the empty section.
        
        // We need to fetch any segments resulting from the merge/deletion
        const newSegmentsToFetch = deleteSection(sectionIdx, updatedSections);
        segmentsToFetch = [...segmentsToFetch, ...newSegmentsToFetch];
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
      
      const segmentsToFetch = deleteSection(sectionIdx, updatedSections);
      
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



  const handlePointRename = (sectionIdx, pointIdx, newName) => {
      const updatedSections = [...sections];
      updatedSections[sectionIdx].points[pointIdx].name = newName;
      setSections(updatedSections);
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
            segmentsToFetch.push({ sectionIdx: sectionIdx - 1, segmentId: segId, start: lastPointOfPrev, end: currPoint });
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

  const previewGeoJSON = useMemo(() => {
    if (!previewRoute) return null;
    const invalids = [];
    const features = previewRoute.sections.flatMap((sec, secIdx) =>
      sec.segments
        .map((seg, segIdx) => ({ geometry: seg.geometry, seg, secIdx, segIdx }))
        .filter(({ geometry, seg, secIdx, segIdx }) => {
          const geom = geometry;
          const ok =
            geom &&
            geom.type === 'LineString' &&
            Array.isArray(geom.coordinates) &&
            geom.coordinates.length >= 2 &&
            geom.coordinates.every(
              (c) =>
                Array.isArray(c) &&
                c.length >= 2 &&
                Number.isFinite(c[0]) &&
                Number.isFinite(c[1])
            );
          if (!ok) {
            invalids.push({
              secIdx,
              segIdx,
              type: geom?.type ?? null,
              coordinatesLen: Array.isArray(geom?.coordinates) ? geom.coordinates.length : null,
            });
          }
          return ok;
        })
        .map(({ geometry }) => ({
          type: 'Feature',
          geometry,
          properties: { type: 'preview' },
        }))
    );
    if (invalids.length > 0 && !previewInvalidLoggedRef.current) {
      console.warn('[previewGeoJSON] Dropping invalid segments', invalids.slice(0, 5));
      previewInvalidLoggedRef.current = true;
    }
    if (features.length === 0) return null;
    return {
      type: 'FeatureCollection',
      features,
    };
  }, [previewRoute]);

  // Animated Dash Array (Marching Ants)
  React.useEffect(() => {
      if (!previewRoute || !previewGeoJSON || !mapRef.current) {
          if (animationRef.current) {
              cancelAnimationFrame(animationRef.current);
              animationRef.current = null;
          }
          return;
      }

      // Smooth marching-ants with finite dash variants (prevents LineAtlas overflow).
      const DASH_LEN = 3;
      const GAP_LEN = 1;
      const STEP_COUNT = 64;
      const STEP_MS = 50;
      const TOTAL = DASH_LEN + GAP_LEN;
      const makeDashFrame = (progress) => {
          if (progress < DASH_LEN) {
              // Shift starts within a dash segment.
              return [DASH_LEN - progress, GAP_LEN, progress, 0];
          }
          // Shift starts within a gap segment.
          const gapProgress = progress - DASH_LEN;
          return [0, GAP_LEN - gapProgress, DASH_LEN, gapProgress];
      };
      const DASH_SEQUENCE = Array.from({ length: STEP_COUNT + 1 }, (_, idx) =>
          makeDashFrame((idx / STEP_COUNT) * TOTAL)
      );
      let isCancelled = false;
      let lastStep = -1;

      const animateDash = (timestamp) => {
          if (isCancelled) return;
          const forwardStep = Math.floor(timestamp / STEP_MS) % DASH_SEQUENCE.length;
          const step = (DASH_SEQUENCE.length - 1 - forwardStep + DASH_SEQUENCE.length) % DASH_SEQUENCE.length;
          
          const mapInstance = mapRef.current?.getMap ? mapRef.current.getMap() : mapRef.current;
          
          if (
              step !== lastStep &&
              mapInstance &&
              mapInstance.getLayer &&
              mapInstance.getLayer('preview-layer')
          ) {
              lastStep = step;
              try {
                  mapInstance.setPaintProperty('preview-layer', 'line-dasharray', DASH_SEQUENCE[step]); 
              } catch (err) {
                  // Keep animation loop alive if layer gets replaced during render.
              }
          }
          animationRef.current = requestAnimationFrame(animateDash);
      };

      const mapInstance = mapRef.current?.getMap ? mapRef.current.getMap() : mapRef.current;
      const startAnimation = () => {
          if (isCancelled) return;
          if (animationRef.current) cancelAnimationFrame(animationRef.current);
          animationRef.current = requestAnimationFrame(animateDash);
      };

      if (mapInstance && mapInstance.isStyleLoaded && !mapInstance.isStyleLoaded()) {
          mapInstance.once('idle', startAnimation);
      } else {
          startAnimation();
      }

      return () => {
          isCancelled = true;
          if (mapInstance && mapInstance.off) mapInstance.off('idle', startAnimation);
          if (animationRef.current) cancelAnimationFrame(animationRef.current);
      };
  }, [previewRoute, previewGeoJSON]);



  const openSaveModal = () => {
    if (!auth.currentUser) {
        if (confirm("Login is required to save routes. Sign in with Google now?")) {
            loginWithGoogle();
        }
        return;
    }
    setIsSaveModalOpen(true);
  };

  const handleSaveRoute = async (modalData) => {
      setIsSaveModalOpen(false);
      setIsLoading(true);
      setLoadingMsg(modalData.isOverwrite ? 'Updating Route...' : 'Saving New Route...');

      try {
          const idToken = await auth.currentUser.getIdToken();
          
          // Simplified Payload: Only Editor State
          const payload = {
              title: modalData.title,
              description: modalData.description,
              status: modalData.status,
              tags: modalData.tags,
              is_overwrite: modalData.isOverwrite,
              parent_route_id: modalData.isOverwrite ? null : currentRouteId,
              // These values are informational for the initial request, 
              // backend will recalculate using Valhalla for consistency.
              summary_path: [{lat: 37.5, lon: 127.0}], // Placeholder, backend generates
              distance: 0, 
              elevation_gain: 0,
              // Backend generates full_data using Valhalla
              full_data: null, 
              editor_state: {
                  sections: sections
              }
          };

          if (modalData.isOverwrite && currentRouteId) {
             payload.route_id = currentRouteId;
          }

          const res = await fetch('/api/routes', {
              method: 'POST',
              headers: {
                  'Content-Type': 'application/json',
                  'Authorization': `Bearer ${idToken}`
              },
              body: JSON.stringify(payload)
          });

          if (!res.ok) {
              const err = await res.json();
              throw new Error(err.detail || 'Failed to save');
          }

          const result = await res.json();
          alert(modalData.isOverwrite ? "Route updated!" : "Route saved successfully!");
          
          // Update local state with saved metadata
          setCurrentRouteId(result.route_id);
          setRouteName(modalData.title);
          setRouteDescription(modalData.description);
          setRouteStatus(modalData.status);
          setRouteTags(modalData.tags);
          setRouteOwnerId(auth.currentUser.uid); // Assuming current user is now owner
          setIsDirty(false); // Changes saved
          setIsMenuOpen(false);
          setIsSearchOpen(false);
      } catch (e) {
          console.error(e);
          alert(`Error saving route: ${e.message}`);
      } finally {
          setIsLoading(false);
          setLoadingMsg('');
      }
  };

  const fitMapToSections = useCallback((sectionsToFit) => {
    if (!mapRef.current || !sectionsToFit || sectionsToFit.length === 0) return;

    let minLng = 180, maxLng = -180, minLat = 90, maxLat = -90;
    let hasPoints = false;

    sectionsToFit.forEach(section => {
        // Check segments (detailed geometry)
        section.segments?.forEach(segment => {
            segment.geometry?.coordinates?.forEach(coord => {
                const [lng, lat] = coord;
                if (lng < minLng) minLng = lng;
                if (lng > maxLng) maxLng = lng;
                if (lat < minLat) minLat = lat;
                if (lat > maxLat) maxLat = lat;
                hasPoints = true;
            });
        });
        // Check points (markers) - crucial if no segments yet
        section.points?.forEach(p => {
             const lng = p.lng;
             const lat = p.lat;
             if (lng < minLng) minLng = lng;
             if (lng > maxLng) maxLng = lng;
             if (lat < minLat) minLat = lat;
             if (lat > maxLat) maxLat = lat;
             hasPoints = true;
        });
    });

    if (hasPoints) {
        // Add some padding/buffer if it's a single point or very small area
        if (Math.abs(maxLng - minLng) < 0.0001 && Math.abs(maxLat - minLat) < 0.0001) {
            const buffer = 0.01;
            minLng -= buffer; maxLng += buffer;
            minLat -= buffer; maxLat += buffer;
        }

        try {
            mapRef.current.fitBounds(
                [[minLng, minLat], [maxLng, maxLat]],
                { padding: 100, duration: 1000 }
            );
        } catch (e) {
            console.error("Fit bounds error:", e);
        }
    }
  }, []);

  const handleImportGPX = async (file) => {
      setIsLoading(true);
      setLoadingMsg('Importing GPX...');
      try {
          const formData = new FormData();
          formData.append('file', file);

          const res = await fetch('/api/routes/import', {
              method: 'POST',
              body: formData
          });

          if (!res.ok) {
              const errData = await res.json().catch(() => ({}));
              throw new Error(errData.detail || 'Failed to import GPX');
          }

          const data = await res.json();
          const { waypoints, full_geometry, summary, display_geojson } = data;
          
          if (!full_geometry || !full_geometry.coordinates || full_geometry.coordinates.length < 2) {
              throw new Error("GPX file has insufficient coordinates.");
          }
          
          let newSections = [];
          
          // Strategy: Reconstruct from Waypoints if available
          if (waypoints && waypoints.length > 0) {
              // 1. Sort waypoints by index
              waypoints.sort((a, b) => a.index - b.index);

              // 2. Group into sections based on 'section_start' type
              let currentSection = null;
              
              // Helper to create a new section
              const createSection = (name, color) => ({
                  id: generateId(),
                  name: name || `Section ${newSections.length + 1}`,
                  points: [],
                  segments: [],
                  color: color || SECTION_COLORS[newSections.length % SECTION_COLORS.length]
              });

              // Initial Section (if first waypoint is not a section start)
              if (waypoints[0].type !== 'section_start') {
                  currentSection = createSection('Imported Section', SECTION_COLORS[0]);
                  newSections.push(currentSection);
              }

              for (const wpt of waypoints) {
                  if (wpt.type === 'section_start') {
                      currentSection = createSection(wpt.name, wpt.color);
                      newSections.push(currentSection);
                  }
                  
                  // Add point to current section
                  if (currentSection) {
                      currentSection.points.push({
                          id: generateId(),
                          lng: wpt.lon,
                          lat: wpt.lat,
                          type: wpt.type, // 'section_start' or 'via'
                          name: wpt.name
                      });
                  }
              }

              // 3. Reconstruct Segments between points
              const allCoords = full_geometry.coordinates; // [[lon, lat, ele], ...]
              const globalFeatures = display_geojson?.features || [];

              for (const section of newSections) {
                  for (let i = 0; i < section.points.length - 1; i++) {
                      const p1 = section.points[i];
                      const p2 = section.points[i+1];
                      
                      const wpt1 = waypoints.find(w => w.lon === p1.lng && w.lat === p1.lat); 
                      const wpt2 = waypoints.find(w => w.lon === p2.lng && w.lat === p2.lat);
                      
                      let segmentGeo = { type: 'LineString', coordinates: [[p1.lng, p1.lat], [p2.lng, p2.lat]] };
                      let dist = 0;
                      let ascent = 0;
                      let surfaceSegments = [];

                      if (wpt1 && wpt2) {
                          const idx1 = wpt1.index;
                          const idx2 = wpt2.index;
                          
                          if (idx1 < idx2 && idx2 < allCoords.length) {
                              // A. Geometry Slicing (Preserve Elevation!)
                              const sliced = allCoords.slice(idx1, idx2 + 1);
                              segmentGeo = { type: 'LineString', coordinates: sliced };
                              
                              // B. Calculate Stats
                              for (let k = 0; k < sliced.length - 1; k++) {
                                  const c1 = sliced[k];
                                  const c2 = sliced[k+1];
                                  dist += getDistance(c1[1], c1[0], c2[1], c2[0]);
                                  
                                  // Ascent (using elevation if available)
                                  if (c1.length > 2 && c2.length > 2) {
                                      const diff = c2[2] - c1[2];
                                      if (diff > 0) ascent += diff;
                                  }
                              }

                              // C. Map Surface Info
                              // Find features that overlap with [idx1, idx2]
                              surfaceSegments = globalFeatures.filter(f => {
                                  const sIdx = f.properties.start_index;
                                  const eIdx = f.properties.end_index;
                                  if (sIdx === undefined || eIdx === undefined) return false;
                                  
                                  // Check overlap: Feature interval [sIdx, eIdx] overlaps with Segment interval [idx1, idx2]
                                  return Math.max(idx1, sIdx) <= Math.min(idx2, eIdx);
                              }).map(f => {
                                  // Pass through the feature. 
                                  // Note: The feature geometry might extend beyond this segment, 
                                  // but for visualization it provides the correct surface type and color.
                                  // If precise clipping is needed, we would slice f.geometry.coordinates here.
                                  return f; 
                              });
                          }
                      }

                      section.segments.push({
                          id: generateId(),
                          startPointId: p1.id,
                          endPointId: p2.id,
                          geometry: segmentGeo,
                          distance: dist,
                          ascent: ascent,
                          type: 'api',
                          surfaceSegments: surfaceSegments
                      });
                  }
              }
              
          } else {
              // Fallback: Use Start and End of the entire track
              const startCoord = full_geometry.coordinates[0];
              const endCoord = full_geometry.coordinates[full_geometry.coordinates.length - 1];

              const startPoint = { id: generateId(), lng: startCoord[0], lat: startCoord[1], type: 'via', name: 'Start' };
              const endPoint = { id: generateId(), lng: endCoord[0], lat: endCoord[1], type: 'via', name: 'End' };

              const newSegment = {
                  geometry: full_geometry,
                  distance: summary.distance,
                  ascent: summary.ascent,
                  type: 'api',
                  surfaceSegments: display_geojson.features
              };

              newSections = [{
                  id: generateId(),
                  name: 'Imported Route',
                  points: [startPoint, endPoint],
                  segments: [newSegment],
                  color: SECTION_COLORS[0]
              }];
          }

          saveToHistory(sections);
          setSections(newSections);
          
          setCurrentRouteId(null);
          setRouteName('Imported GPX');
          setRouteDescription('Imported from GPX file');
          setRouteStatus('PUBLIC');
          setRouteTags([]);
          setRouteOwnerId(null);
          setRouteStats({ views: 0, downloads: 0 });

          // Focus map using helper
          fitMapToSections(newSections);

          setIsMenuOpen(false);
          alert("GPX imported successfully!");

      } catch (err) {
          console.error(err);
          alert("Error importing GPX: " + err.message);
      } finally {
          setIsLoading(false);
          setLoadingMsg('');
      }
  };

  const handleLoadRoute = async (routeId, skipConfirm = false) => {
      if (!skipConfirm && sections.some(s => s.points.length > 0)) {
          if (!confirm("Current route will be discarded. Load new route?")) return;
      }
      setIsLoading(true);
      setLoadingMsg('Loading Route...');

      try {
          const headers = {};
          if (auth.currentUser) {
              const idToken = await auth.currentUser.getIdToken();
              headers['Authorization'] = `Bearer ${idToken}`;
          }

          const res = await fetch(`/api/routes/${routeId}`, { headers });

          if (!res.ok) throw new Error("Failed to load route data");
          
          const data = await res.json();
          
          if (data.editor_state && data.editor_state.sections) {
              setSections(data.editor_state.sections);
              
              // Update all metadata to enable Correct Fork/Overwrite behavior
              setCurrentRouteId(data.route_id);
              setRouteName(data.title || '');
              setRouteDescription(data.description || '');
              setRouteStatus(data.status || 'PUBLIC');
              setRouteTags(data.tags || []);
              setRouteOwnerId(data.owner_id);
              setRouteStats(data.stats || { views: 0, downloads: 0 });
              
              setHistory({ past: [], future: [] }); // Reset history
              setIsDirty(false); // Freshly loaded
              setIsMenuOpen(false);
              setIsSearchOpen(false);
              
              // Focus Map
              fitMapToSections(data.editor_state.sections);

              if (!skipConfirm) alert("Route loaded!");
          } else {
              alert("This route data is missing editor state (Legacy format?). Cannot load into editor.");
          }

      } catch (e) {
          console.error(e);
          alert(`Error loading route: ${e.message}`);
      } finally {
          setIsLoading(false);
          setLoadingMsg('');
      }
  };

  // Auto-load route from URL
  React.useEffect(() => {
    if (initialRouteId) {
      handleLoadRoute(initialRouteId, true);
    }
  }, [initialRouteId]);

  // Toggle handlers for SidebarNav
  const toggleMenu = () => {
    setIsMenuOpen(prev => {
        const newState = !prev;
        if (newState) setIsSearchOpen(false); // Close search if menu opens
        return newState;
    });
  };

  const toggleSearch = () => {
    setIsSearchOpen(prev => {
        const newState = !prev;
        if (newState) setIsMenuOpen(false); // Close menu if search opens
        return newState;
    });
  };

  const handleNewRoute = () => {
    if (sections.some(s => s.points.length > 0)) {
        if (!confirm("Your unsaved changes will be lost. Create a new route?")) return;
    }
    setSections([{ id: generateId(), name: 'Section 1', points: [], segments: [], color: SECTION_COLORS[0] }]);
    setRouteName('');
    setRouteDescription('');
    setRouteStatus('PUBLIC');
    setRouteTags([]);
    setCurrentRouteId(null);
    setRouteOwnerId(null);
    setHistory({ past: [], future: [] });
    setIsDirty(false);
    setIsMenuOpen(false);
    setIsSearchOpen(false);
  };

  const isClean = sections.length === 1 && sections[0].points.length === 0;

  // Preview stats: prefer DB values (same source as Library), fallback to editor_state sums.
  const previewDistLocalKm = previewRoute && Array.isArray(previewRoute.sections)
    ? previewRoute.sections.reduce((acc, sec) => acc + (sec.segments || []).reduce((sAcc, s) => sAcc + (Number(s.distance) || 0), 0), 0)
    : 0;

  const previewAscentLocalM = previewRoute && Array.isArray(previewRoute.sections)
    ? previewRoute.sections.reduce((acc, sec) => acc + (sec.segments || []).reduce((sAcc, s) => sAcc + (Number(s.ascent) || 0), 0), 0)
    : 0;

  const previewDistKm = previewRoute && Number.isFinite(Number(previewRoute?.data?.distance))
    ? Number(previewRoute.data.distance) / 1000
    : previewDistLocalKm;

  const previewAscentM = previewRoute && Number.isFinite(Number(previewRoute?.data?.elevation_gain))
    ? Number(previewRoute.data.elevation_gain)
    : previewAscentLocalM;


  return (
    <div className="flex w-full h-full relative overflow-hidden">
      {/* 1. Left Sidebar Navigation (Toolbar) */}
      <SidebarNav 
        isMenuOpen={isMenuOpen} 
        isSearchOpen={isSearchOpen} 
        onToggleMenu={toggleMenu} 
        onToggleSearch={toggleSearch} 
        onNewRoute={handleNewRoute}
        onImportGPX={handleImportGPX}
        onExportGPX={handleOpenExportModal}
        isClean={isClean}
      />

      {/* 2. Panels Container (Stackable) */}
      <div className="absolute top-0 left-0 h-full z-40 pointer-events-none flex md:relative md:shrink-0 md:pointer-events-auto">
        {/* Menu Panel */}
        <div className={`
            ${isMenuOpen ? 'w-80 border-r border-gray-800 pointer-events-auto shadow-2xl' : 'w-0'} 
            h-full bg-gray-900 overflow-hidden transition-all duration-300 ease-in-out
        `}>
            <div className="w-80 h-full"> {/* Inner Fixed Width Container */}
                <MenuPanel 
                    currentRouteId={currentRouteId}
                    routeStats={routeStats}
                    history={history}
                    onUndo={handleUndo}
                    onRedo={handleRedo}
                    onClear={() => { saveToHistory(sections); setSections([{ id: generateId(), name: 'Section 1', points: [], segments: [], color: SECTION_COLORS[0] }]); }}
                    onSave={openSaveModal}
                    onDownloadGPX={handleOpenExportModal}
                    sections={sections}
                    onPointRemove={handlePointRemove}
                    onPointRename={handlePointRename}
                    onSplitSection={handleSplitSection}
                    onSectionHover={handleSectionHover}
                    onSectionDelete={handleSectionDelete}
                    onSectionMerge={handleSectionMerge}
                    onSectionRename={handleSectionRename}
                    onSectionDownload={handleSectionDownload}
                    onImportGPX={handleImportGPX}
                    isMockMode={isMockMode}
                    setIsMockMode={setIsMockMode}
                />
            </div>
        </div>

        {/* Search Panel */}
        <div className={`
            ${isSearchOpen ? 'w-80 border-r border-gray-800 pointer-events-auto shadow-2xl' : 'w-0'} 
            h-full bg-gray-900 overflow-hidden transition-all duration-300 ease-in-out
        `}>
             <div className="w-80 h-full"> {/* Inner Fixed Width Container */}
                <SearchPanel onLoadRoute={handlePreviewRoute} />
             </div>
        </div>
      </div>

      {/* 3. Main Content (Right) - Map & Chart */}
      <div className="flex-1 flex flex-col relative h-full min-w-0">
        {isLoading && <div className="absolute inset-0 z-[9999] bg-black/30 backdrop-blur-[2px] flex flex-col items-center justify-center"><div className="animate-spin rounded-full h-12 w-12 border-b-4 border-riduck-primary mb-4"></div><div className="text-white font-bold text-lg animate-pulse">{loadingMsg}</div></div>}
        
        {/* Map Area */}
        <div className="flex-1 relative">
                        {/* Top Right: Tools Container */}
            <div className="absolute top-4 right-4 md:top-6 md:right-6 z-10 flex flex-col items-end gap-3 pointer-events-none">
                {/* 1. Straight Line Mode Toggle */}
                <button 
                    onClick={() => setIsMockMode(!isMockMode)}
                    className={`pointer-events-auto flex items-center justify-between gap-2 md:gap-4 px-3 py-2 md:px-5 md:py-3 rounded-2xl border shadow-xl backdrop-blur-md transition-all duration-300 ${
                        isMockMode 
                        ? 'bg-riduck-primary/90 border-riduck-primary text-white shadow-riduck-primary/20' 
                        : 'bg-gray-900/90 border-gray-700 text-gray-400 hover:text-white hover:border-gray-500'
                    }`}
                >
                    <div className="flex flex-col items-start text-left mr-1 md:mr-2 leading-tight">
                        {/* Mobile: Stacked Text */}
                        <span className="text-[10px] font-bold md:hidden">Direct</span>
                        <span className="text-[10px] font-bold md:hidden">Mode</span>
                        
                        {/* Desktop: Full Title & Desc */}
                        <span className="hidden md:inline text-sm font-bold whitespace-nowrap">Direct Mode</span>
                        <span className="text-[10px] opacity-70 font-medium hidden md:block">Draw direct lines</span>
                    </div>
                    
                    {/* Switch Indicator */}
                    <div className={`w-8 h-4 md:w-10 md:h-5 rounded-full relative transition-colors flex-shrink-0 ${isMockMode ? 'bg-black/20' : 'bg-gray-700'}`}>
                        <div className={`absolute top-0.5 left-0.5 w-3 h-3 md:w-4 md:h-4 rounded-full bg-white shadow-sm transition-transform duration-200 ${isMockMode ? 'translate-x-4 md:translate-x-5' : 'translate-x-0'}`} />
                    </div>
                </button>

                {/* 2. Place Search Bar (Floating) */}
                <div className={`pointer-events-auto flex items-center bg-gray-900/90 backdrop-blur-md border border-gray-700 shadow-xl rounded-full transition-all duration-300 ease-in-out h-10 md:h-12 overflow-hidden ${isPlaceSearchOpen ? 'w-64 px-4' : 'w-10 md:w-12 justify-center'}`}>
                    
                    {/* Input Field (Visible only when open) */}
                    <input 
                        type="text"
                        placeholder="Not supported yet (미지원)"
                        value={placeSearchQuery}
                        onChange={(e) => setPlaceSearchQuery(e.target.value)}
                        disabled
                        className={`bg-transparent text-gray-500 text-sm outline-none transition-all duration-300 h-full ${isPlaceSearchOpen ? 'flex-1 opacity-100' : 'w-0 opacity-0'}`}
                    />

                    {/* Toggle Button (Magnifying Glass) */}
                    <button 
                        onClick={() => {
                            if (!isPlaceSearchOpen) {
                                setIsPlaceSearchOpen(true);
                            } else {
                                alert("Place search is not supported yet (미지원).");
                                setIsPlaceSearchOpen(false);
                            }
                        }}
                        className={`text-gray-400 hover:text-white transition-colors shrink-0 flex items-center justify-center ${isPlaceSearchOpen ? 'ml-2' : ''}`}
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 md:h-6 md:w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={isPlaceSearchOpen && placeSearchQuery ? "M6 18L18 6M6 6l12 12" : "M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"} />
                        </svg>
                    </button>
                </div>
            </div>

            {/* Stats Overlay */}
            <div className="absolute top-4 left-4 md:top-6 md:left-6 z-10 bg-gray-900/90 backdrop-blur-md px-5 py-2 md:px-8 md:py-3 rounded-2xl border border-gray-700 shadow-2xl flex gap-4 md:gap-8 items-center pointer-events-none transition-all">
                <div className="text-center">
                    <p className="text-[8px] md:text-[10px] text-gray-400 uppercase font-bold tracking-wider">Distance</p>
                    <p className="text-lg md:text-2xl font-mono text-white font-bold">{totalDist.toFixed(1)}<span className="text-xs md:text-sm text-gray-500 ml-0.5 font-sans">km</span></p>
                </div>
                <div className="w-px h-6 md:h-8 bg-gray-700"></div>
                <div className="text-center">
                    <p className="text-[8px] md:text-[10px] text-gray-400 uppercase font-bold tracking-wider">Ascent</p>
                    <p className="text-lg md:text-2xl font-mono text-white font-bold">{Math.round(totalAscent)}<span className="text-xs md:text-sm text-gray-500 ml-0.5 font-sans">m</span></p>
                </div>
            </div>

            {/* Mobile Only: Sidebar Toggles (Below Stats) */}
            <div className="absolute top-[80px] left-4 z-10 flex gap-2 md:hidden">
                <button 
                    onClick={handleNewRoute}
                    disabled={isClean}
                    className={`p-2.5 rounded-xl border shadow-xl backdrop-blur-md transition-all ${isClean ? 'bg-gray-800/50 border-gray-800 text-gray-600 opacity-50 cursor-not-allowed' : 'bg-gray-900/90 border-gray-700 text-gray-400 hover:text-white hover:bg-gray-800'}`}
                >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                </button>
                <button 
                    onClick={toggleMenu}
                    className={`p-2.5 rounded-xl border shadow-xl backdrop-blur-md transition-all ${isMenuOpen ? 'bg-riduck-primary border-riduck-primary text-white shadow-riduck-primary/20' : 'bg-gray-900/90 border-gray-700 text-gray-400'}`}
                >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
                    </svg>
                </button>
                <button 
                    onClick={toggleSearch}
                    className={`p-2.5 rounded-xl border shadow-xl backdrop-blur-md transition-all ${isSearchOpen ? 'bg-riduck-primary border-riduck-primary text-white shadow-riduck-primary/20' : 'bg-gray-900/90 border-gray-700 text-gray-400'}`}
                >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.58 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.58 4 8 4s8-1.79 8-4M4 7c0-2.21 3.58-4 8-4s8 1.79 8 4" />
                    </svg>
                </button>
                <label className={`p-2.5 rounded-xl border shadow-xl backdrop-blur-md transition-all bg-gray-900/90 border-gray-700 text-gray-400 hover:text-white hover:bg-gray-800 cursor-pointer flex items-center justify-center`}>
                    <input type="file" accept=".gpx,.tcx" className="hidden" onChange={(e) => {
                        const file = e.target.files[0];
                        if (file) {
                            handleImportGPX(file);
                            e.target.value = '';
                        }
                    }} />
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                    </svg>
                </label>
                <button 
                    onClick={handleOpenExportModal}
                    disabled={isClean}
                    className={`p-2.5 rounded-xl border shadow-xl backdrop-blur-md transition-all ${isClean ? 'bg-gray-800/50 border-gray-800 text-gray-600 opacity-50 cursor-not-allowed' : 'bg-gray-900/90 border-gray-700 text-gray-400 hover:text-white hover:bg-gray-800'}`}
                >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                </button>
            </div>

            <Map 
                ref={mapRef} 
                initialViewState={INITIAL_VIEW_STATE} 
                mapStyle="https://api.maptiler.com/maps/jp-mierune-dark/style.json?key=hmAnzLL30c4tItQZZ8B9" 
                onLoad={handleMapLoad}
                onClick={handleMapClick}
                onMouseMove={onHover}
                
                onTouchStart={handleTouchStart}
                onTouchMove={handleTouchMove}
                onTouchEnd={handleTouchEnd}

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

                {previewGeoJSON && (
                    <Source id="preview-source" type="geojson" data={previewGeoJSON}>
                        <Layer 
                            id="preview-layer" 
                            type="line" 
                            layout={{ 'line-join': 'round', 'line-cap': 'butt' }} 
                            paint={{ 
                                'line-color': '#FF4081', // Pink/Magenta
                                'line-width': 5, 
                                'line-opacity': 0.9,
                                'line-dasharray': [3, 1] // [dash length, gap length] relative to line-width
                            }} 
                        />
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
                     if (
                         !Number.isFinite(startP.lng) ||
                         !Number.isFinite(startP.lat) ||
                         !Number.isFinite(endP.lng) ||
                         !Number.isFinite(endP.lat) ||
                         !Number.isFinite(dragState.lng) ||
                         !Number.isFinite(dragState.lat)
                     ) {
                         if (!dragPreviewInvalidLoggedRef.current) {
                             console.warn('[drag-preview] Invalid coordinates', {
                                 start: [startP.lng, startP.lat],
                                 mid: [dragState.lng, dragState.lat],
                                 end: [endP.lng, endP.lat],
                             });
                             dragPreviewInvalidLoggedRef.current = true;
                         }
                         return null;
                     }

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
                        closeButton={false}
                        closeOnClick={false}
                        maxWidth="360px"
                    >
                        <div className="bg-gray-900 text-white rounded-xl shadow-2xl border border-gray-700 overflow-hidden ring-1 ring-white/10 w-full">
                            {/* Custom Close Button */}
                            <button 
                                onClick={() => setAmbiguityPopup(null)}
                                className="absolute top-2 right-2 text-gray-500 hover:text-white hover:bg-white/10 rounded-full p-1 transition-all z-10"
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                            </button>

                            <div className="bg-gray-800 px-4 py-3 border-b border-gray-700 flex justify-between items-center">
                                <span className="text-xs font-bold text-gray-300 uppercase tracking-wider">Select Route Segment</span>
                            </div>
                            <div className="flex flex-col gap-1 p-2 max-h-[280px] overflow-y-auto custom-scrollbar bg-gray-900/95">
                                {ambiguityPopup.candidates.map((cand, idx) => (
                                    <button
                                        key={idx}
                                        className="w-full relative overflow-hidden p-3 rounded-lg bg-gray-800/50 hover:bg-riduck-primary/10 border border-gray-700/50 hover:border-riduck-primary/50 transition-all text-left group flex items-center gap-3"
                                        onClick={() => performInsertPoint(cand, ambiguityPopup.lng, ambiguityPopup.lat)}
                                    >
                                        {/* Color Indicator Bar */}
                                        <div className="absolute left-0 top-0 bottom-0 w-1" style={{ backgroundColor: cand.sectionColor }}></div>
                                        
                                        <div className="flex-1 min-w-0 pl-1">
                                            {/* Top: Distance (Primary Info) */}
                                            <div className="flex items-center gap-2 mb-0.5">
                                                <span className="text-sm font-black text-white group-hover:text-riduck-primary transition-colors font-mono tracking-tight">
                                                    {cand.totalDistance.toFixed(1)} km
                                                </span>
                                                <span className="text-[10px] text-gray-500 font-medium uppercase tracking-wider bg-gray-800 px-1.5 py-0.5 rounded">Point</span>
                                            </div>
                                            
                                            {/* Bottom: Context (Waypoints) - Improved Layout */}
                                            <div className="flex items-center gap-2 text-xs text-gray-400 w-full mt-1">
                                                <div className="flex-1 min-w-0 flex items-center gap-1.5 overflow-hidden">
                                                    <span className="font-bold text-gray-200 truncate">{cand.startPointName}</span>
                                                    <span className="text-gray-600 shrink-0">➔</span>
                                                    <span className="font-bold text-gray-200 truncate">{cand.endPointName}</span>
                                                </div>
                                            </div>
                                        </div>
                                        
                                        {/* Right: Section Badge */}
                                        <div className="shrink-0 px-2 py-1 bg-gray-900/80 rounded text-[10px] font-bold text-gray-500 border border-gray-700 group-hover:text-riduck-primary/80 group-hover:border-riduck-primary/30 transition-colors">
                                            {cand.sectionName}
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

            {/* Preview Control UI (Floating Above Map) */}
            {previewRoute && (
                <div className="absolute inset-x-0 bottom-3 md:bottom-6 z-30 flex justify-center px-3 md:px-6 pointer-events-none animate-fadeInUp">
                    <div className="pointer-events-auto w-full max-w-[360px] md:max-w-[440px] bg-gray-900/95 backdrop-blur-xl border border-gray-700/50 shadow-2xl rounded-2xl p-4">
                        <div className="flex flex-col gap-4">
                            {/* Header Info */}
                            <div className="flex justify-between items-start gap-3">
                                <div className="min-w-0">
                                    <h3 className="text-white font-bold text-base md:text-lg leading-tight truncate">{previewRoute.data.title || 'Untitled Route'}</h3>
                                    <div className="flex items-center gap-3 mt-1 text-xs text-gray-400 font-mono">
                                        <span>{previewDistKm.toFixed(1)}km</span>
                                        <span className="w-1 h-1 rounded-full bg-gray-600"></span>
                                        <span>+{Math.round(previewAscentM)}m</span>
                                    </div>
                                </div>
                                <span className="shrink-0 bg-riduck-primary/20 text-riduck-primary text-[10px] font-bold px-2 py-1 rounded border border-riduck-primary/30 uppercase tracking-wider">Preview</span>
                            </div>

                            {/* Actions */}
                            <div className="grid grid-cols-2 gap-3">
                                <button 
                                    onClick={() => cancelPreview()}
                                    className="py-3 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 font-bold text-sm transition-all active:scale-[0.98]"
                                >
                                    Cancel
                                </button>
                                <button 
                                    onClick={confirmPreviewLoad}
                                    className="py-3 rounded-xl bg-riduck-primary hover:bg-riduck-primary/90 text-white font-bold text-sm shadow-lg shadow-riduck-primary/20 transition-all active:scale-[0.98] flex items-center justify-center gap-2"
                                >
                                    Load Route
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>

        {/* Elevation Chart (Bottom Fixed with Padding) */}
        <div className="h-40 md:h-52 border-t border-gray-800 bg-gray-900/90 backdrop-blur-md relative z-10 px-4 pb-6 pt-2 shrink-0">
            <ElevationChart segments={sections.flatMap(s => s.segments)} onHoverPoint={handleHoverPoint} />
        </div>

        {/* Save Route Modal */}
        <SaveRouteModal 
            isOpen={isSaveModalOpen}
            onClose={() => setIsSaveModalOpen(false)}
            onSave={handleSaveRoute}
            isLoading={isLoading}
            isOwner={user && (routeOwnerId === user.uid || routeOwnerId === user.id)}
            isMapChanged={isDirty}
            initialData={{
                id: currentRouteId,
                title: routeName,
                description: routeDescription,
                status: routeStatus,
                tags: routeTags
            }}
        />
        
        <ExportRouteModal
            isOpen={isExportModalOpen}
            onClose={() => setIsExportModalOpen(false)}
            onExport={performExport}
            initialTitle={routeName}
        />
      </div>
    </div>
  );
};

export default BikeRoutePlanner;
