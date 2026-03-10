import React, { useState, useCallback, useRef, useMemo } from 'react';
import apiClient from '../utils/apiClient';
import { Map, Source, Layer, Marker, Popup } from 'react-map-gl/maplibre';
import { useAuth } from '../AuthContext';
import { auth } from '../firebase';
import 'maplibre-gl/dist/maplibre-gl.css';
import ElevationChart from './ElevationChart';
import SidebarNav from './SidebarNav';
import MenuPanel from './MenuPanel';
import SearchPanel from './SearchPanel';
import WaypointPanel from './WaypointPanel';
import WaypointDetailModal from './WaypointDetailModal';
import SaveRouteModal from './SaveRouteModal';
import ExportRouteModal from './ExportRouteModal';
import NearbyFilterModal, { DEFAULT_FILTERS } from './NearbyFilterModal';
import ReactMarkdown from 'react-markdown';
import { getPointTier, POINT_TYPE_CONFIG, TIER_STYLES } from '../utils/waypointTypes';
import posthog from 'posthog-js';
import { analytics } from '../utils/analytics';

const formatDate = (dateString) => {
    if (!dateString) return null;
    const d = new Date(dateString);
    const now = new Date();
    if ((now - d) < 86400000) {
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        const hh = String(d.getHours()).padStart(2, '0');
        const min = String(d.getMinutes()).padStart(2, '0');
        return `${mm}.${dd} ${hh}:${min}`;
    }
    const y = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${y}.${mm}.${dd}`;
};

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
  const [isElevationChartVisible, setIsElevationChartVisible] = useState(true);
  
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
  const [sectionsVersion, setSectionsVersion] = useState(0); // Increments on route edits

  // Route Metadata (Received via props)
  const [routeDescription, setRouteDescription] = useState('');
  const [routeStatus, setRouteStatus] = useState('PUBLIC');
  const [routeTags, setRouteTags] = useState([]);
  const [currentRouteId, setCurrentRouteId] = useState(null);
  const [routeUuid, setRouteUuid] = useState(null);
  const [routeStats, setRouteStats] = useState({ views: 0, downloads: 0 });
  const [routeOwnerId, setRouteOwnerId] = useState(null);
  const [isSaveModalOpen, setIsSaveModalOpen] = useState(false);
  const [isExportModalOpen, setIsExportModalOpen] = useState(false);
  const [searchRefreshTrigger, setSearchRefreshTrigger] = useState(0);
  const [focusedPointId, setFocusedPointId] = useState(null);
  const [mapHoverCoord, setMapHoverCoord] = useState(null);

  // Preview State
  const [previewRoute, setPreviewRoute] = useState(null);
  const [mobilePreviewExpanded, setMobilePreviewExpanded] = useState(false);
  const [previewLinkCopied, setPreviewLinkCopied] = useState(false);

  // Place Search State
  const [isPlaceSearchOpen, setIsPlaceSearchOpen] = useState(false);
  const [placeSearchQuery, setPlaceSearchQuery] = useState('');
  const [placeSearchResults, setPlaceSearchResults] = useState([]);
  const [placeSearchLoading, setPlaceSearchLoading] = useState(false);
  const placeSearchTimerRef = useRef(null);
  const [placeSearchPulse, setPlaceSearchPulse] = useState(null); // { lon, lat }
  const pulseTimerRef = useRef(null);

  // More Menu State (Mobile)
  const [moreMenuOpen, setMoreMenuOpen] = useState(false);
  const moreMenuRef = useRef(null);

  // Nearby Routes State
  const [isNearbyMode, setIsNearbyMode] = useState(false);
  const [nearbyRoutes, setNearbyRoutes] = useState(null);
  const [nearbyCenter, setNearbyCenter] = useState(null); // { lat, lng, radiusKm }
  const [routeFilters, setRouteFilters] = useState({ ...DEFAULT_FILTERS });
  const [isNearbyFilterOpen, setIsNearbyFilterOpen] = useState(false);
  const routeFiltersRef = useRef(routeFilters);
  const nearbyDebounceRef = useRef(null);

  // Waypoint Mode State
  const [isWaypointMode, setIsWaypointMode] = useState(false);
  const [adminWaypoints, setAdminWaypoints] = useState([]);
  const [selectedWaypointId, setSelectedWaypointId] = useState(null);

  // Long Press State for Mobile
  const longPressTimerRef = useRef(null);
  const isLongPressRef = useRef(false);
  const touchStartPosRef = useRef(null);

  // Animation Ref
  const animationRef = useRef(null);
  const previewInvalidLoggedRef = useRef(false);
  const dragPreviewInvalidLoggedRef = useRef(false);
  const previewPanelMobileRef = useRef(null);
  const pendingNearbyAfterSaveRef = useRef(false);

  const makeCircleGeoJSON = (lat, lng, radiusKm, steps = 64) => {
    const coords = [];
    const dx = radiusKm / (111.32 * Math.cos(lat * Math.PI / 180));
    const dy = radiusKm / 110.574;
    for (let i = 0; i <= steps; i++) {
      const angle = (i / steps) * 2 * Math.PI;
      coords.push([lng + dx * Math.cos(angle), lat + dy * Math.sin(angle)]);
    }
    return { type: 'Feature', geometry: { type: 'Polygon', coordinates: [coords] } };
  };

  const fetchNearbyRoutes = useCallback(async () => {
    if (!mapRef.current) return;
    const map = mapRef.current.getMap ? mapRef.current.getMap() : mapRef.current;
    if (!map) return;

    const center = map.getCenter();
    const zoom = map.getZoom();

    if (zoom < 9) {
        setNearbyRoutes(null);
        setNearbyCenter(null);
        return;
    }

    // zoom 레벨에 따라 검색 반경 조정
    const radius = zoom >= 13 ? 3 : zoom >= 12 ? 5 : zoom >= 11 ? 8 : zoom >= 10 ? 15 : 30;

    setNearbyCenter({ lat: center.lat, lng: center.lng, radiusKm: radius });

    try {
        const f = routeFiltersRef.current;
        const params = new URLSearchParams({
            lat: center.lat, lon: center.lng, radius, limit: f.limit
        });
        if (f.minDistance !== '') params.set('min_distance', f.minDistance);
        if (f.maxDistance !== '') params.set('max_distance', f.maxDistance);
        if (f.minElevation !== '') params.set('min_elevation', f.minElevation);
        if (f.maxElevation !== '') params.set('max_elevation', f.maxElevation);
        if (f.tags.length > 0) params.set('tags', f.tags.join(','));

        const data = await apiClient.get(`/api/routes/nearby?${params}`);
        setNearbyRoutes(data);
    } catch (e) {
        console.error("Failed to fetch nearby routes:", e);
    }
  }, []);

  const toggleNearby = () => {
      // Clear place search state on mode switch
      closePlaceSearch();
      setIsWaypointMode(false);

      if (!isNearbyMode) {
          // Turning ON nearby mode
          const hasRoute = sections.some(s => s.points.length > 0);
          if (hasRoute) {
              const wantSave = confirm("현재 경로가 있습니다. 저장하시겠습니까?\n(확인: 저장 후 탐색 모드, 취소: 저장 없이 탐색 모드)");
              if (wantSave) {
                  pendingNearbyAfterSaveRef.current = true;
                  openSaveModal();
                  return;
              }
              // User chose not to save — reset and enter nearby mode
              resetRoute();
          }
          setIsNearbyMode(true);
          fetchNearbyRoutes();
      } else {
          // Turning OFF nearby mode
          if (nearbyDebounceRef.current) clearTimeout(nearbyDebounceRef.current);
          setNearbyRoutes(null);
          setNearbyCenter(null);
          setIsNearbyMode(false);
      }
  };

  const toggleWaypointMode = () => {
      closePlaceSearch();
      if (!isWaypointMode) {
          setIsNearbyMode(false);
          setIsWaypointMode(true);
          fetchAdminWaypoints();
      } else {
          setIsWaypointMode(false);
          setAdminWaypoints([]);
      }
  };

  const fetchAdminWaypoints = async () => {
      try {
          const data = await apiClient.get('/api/waypoints');
        setAdminWaypoints(data);
    } catch (e) {
          console.error("Failed to fetch admin waypoints:", e);
      }
  };

  const adminWaypointsGeoJSON = useMemo(() => {
      if (!adminWaypoints || adminWaypoints.length === 0) return null;
      return {
          type: 'FeatureCollection',
          features: adminWaypoints.map(wp => ({
              type: 'Feature',
              geometry: { type: 'Point', coordinates: [wp.lng, wp.lat] },
              properties: {
                  id: wp.id,
                  name: wp.name,
                  description: wp.description,
                  type: wp.type,
                  tour_count: wp.tour_count || 1,
                  has_images: wp.has_images,
                  has_tips: wp.has_tips
              }
          }))
      };
  }, [adminWaypoints]);

  const handleMapMoveEnd = (evt) => {
      if (isNearbyMode) {
          if (nearbyDebounceRef.current) clearTimeout(nearbyDebounceRef.current);
          nearbyDebounceRef.current = setTimeout(() => {
              fetchNearbyRoutes();
          }, 500); // 500ms debounce
      }
  };

  const handleHoverPoint = useCallback((coord) => setHoveredCoord(coord), []);

  const flyMapToPoint = useCallback((coord) => {
    if (!coord || !Number.isFinite(coord.lng) || !Number.isFinite(coord.lat)) return;

    const mapInstance = mapRef.current?.getMap ? mapRef.current.getMap() : mapRef.current;
    if (!mapInstance || typeof mapInstance.flyTo !== 'function') return;

    try {
      const currentZoom = typeof mapInstance.getZoom === 'function' ? mapInstance.getZoom() : undefined;
      mapInstance.flyTo({
        center: [coord.lng, coord.lat],
        zoom: currentZoom,
        duration: 700,
        essential: true
      });
    } catch (err) {
      console.warn('Chart-to-map move failed:', err);
    }
  }, []);

  // Place Search Logic
  const COORD_REGEX = /^[-]?\d{1,3}\.\d+[,\s]+[-]?\d{1,3}\.\d+$/;

  const performPlaceSearch = useCallback(async (query) => {
    const trimmed = query.trim();
    if (!trimmed) {
      setPlaceSearchResults([]);
      return;
    }

    setPlaceSearchLoading(true);
    try {
      if (COORD_REGEX.test(trimmed)) {
        // Coordinate input → Nominatim reverse geocoding
        const parts = trimmed.split(/[,\s]+/).map(Number);
        const [lat, lon] = parts;
        const res = await fetch(
          `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json&accept-language=ko`
        );
        const data = await res.json();
        if (data && data.display_name) {
          setPlaceSearchResults([{
            name: data.display_name.split(',')[0],
            address: data.display_name,
            lat: parseFloat(data.lat),
            lon: parseFloat(data.lon),
          }]);
        } else {
          setPlaceSearchResults([]);
        }
      } else {
        // Text search → Photon autocomplete
        const res = await fetch(
          `https://photon.komoot.io/api/?q=${encodeURIComponent(trimmed)}&limit=5`
        );
        const data = await res.json();
        if (data.features && data.features.length > 0) {
          setPlaceSearchResults(data.features.map(f => {
            const p = f.properties;
            const [lon, lat] = f.geometry.coordinates;
            const nameParts = [p.name, p.city, p.state, p.country].filter(Boolean);
            return {
              name: p.name || nameParts[0] || 'Unknown',
              address: nameParts.join(', '),
              lat,
              lon,
            };
          }));
        } else {
          setPlaceSearchResults([]);
        }
      }
    } catch (err) {
      console.warn('Place search failed:', err);
      setPlaceSearchResults([]);
    } finally {
      setPlaceSearchLoading(false);
    }
  }, []);

  const handlePlaceSearchInput = useCallback((value) => {
    setPlaceSearchQuery(value);
    if (placeSearchTimerRef.current) clearTimeout(placeSearchTimerRef.current);
    placeSearchTimerRef.current = setTimeout(() => {
      performPlaceSearch(value);
    }, 300);
  }, [performPlaceSearch]);

  const handlePlaceSelect = useCallback((result) => {
    const mapInstance = mapRef.current?.getMap ? mapRef.current.getMap() : mapRef.current;
    if (mapInstance && typeof mapInstance.flyTo === 'function') {
      const currentZoom = typeof mapInstance.getZoom === 'function' ? mapInstance.getZoom() : 12;
      mapInstance.flyTo({
        center: [result.lon, result.lat],
        zoom: Math.max(currentZoom, 14),
        duration: 1000,
        essential: true,
      });
    }
    // Show pulse at location
    if (pulseTimerRef.current) clearTimeout(pulseTimerRef.current);
    setPlaceSearchPulse({ lon: result.lon, lat: result.lat });
    pulseTimerRef.current = setTimeout(() => setPlaceSearchPulse(null), 3000);

    setPlaceSearchResults([]);
    setPlaceSearchQuery('');
    setIsPlaceSearchOpen(false);
  }, []);

  const closePlaceSearch = useCallback(() => {
    setPlaceSearchResults([]);
    setPlaceSearchQuery('');
    setIsPlaceSearchOpen(false);
    setPlaceSearchPulse(null);
    if (pulseTimerRef.current) clearTimeout(pulseTimerRef.current);
  }, []);

  const handleChartPointSelect = useCallback((coord) => {
    if (!coord || !Number.isFinite(coord.lng) || !Number.isFinite(coord.lat)) return;
    setFocusedPointId(null);
    setHoveredCoord({ lng: coord.lng, lat: coord.lat });
    flyMapToPoint(coord);
  }, [flyMapToPoint]);

  const handleMenuPointFocus = useCallback((sectionIdx, _pointIdx, point) => {
    if (!point || !Number.isFinite(point.lng) || !Number.isFinite(point.lat)) return;

    const coord = { lng: point.lng, lat: point.lat };
    setFocusedPointId(point.id);
    setHoveredCoord(coord);
    setHoveredSectionIndex(sectionIdx);
    flyMapToPoint(coord);
  }, [flyMapToPoint]);

  // Close more menu on outside click
  React.useEffect(() => {
    if (!moreMenuOpen) return;
    const handleClickOutside = (e) => {
      if (moreMenuRef.current && !moreMenuRef.current.contains(e.target)) {
        setMoreMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, [moreMenuOpen]);

  React.useEffect(() => {
    if (!focusedPointId) return;

    const pointExists = sections.some((section) =>
      section.points?.some((point) => point.id === focusedPointId)
    );

    if (!pointExists) {
      setFocusedPointId(null);
      setHoveredCoord(null);
    }
  }, [sections, focusedPointId]);

  const sectionsWithPointDistances = useMemo(() => {
    if (!Array.isArray(sections)) return [];

    let cumulativeDistKm = 0;

    const getSegmentDistanceKm = (segment, startPoint, endPoint) => {
      const segDist = Number(segment?.distance);
      if (Number.isFinite(segDist) && segDist > 0) return segDist;
      if (startPoint && endPoint) {
        return getDistance(startPoint.lat, startPoint.lng, endPoint.lat, endPoint.lng);
      }
      return 0;
    };

    return sections.map((section, sectionIdx) => {
      const points = Array.isArray(section?.points) ? section.points : [];
      const segmentList = Array.isArray(section?.segments) ? section.segments : [];
      const pointIdSet = new Set(points.map((p) => p.id));
      const distanceByPointId = new globalThis.Map();

      // Build segment lookup map: "startId->endId" → segment (O(n) instead of O(n²) .find())
      const segmentLookup = new globalThis.Map();
      for (const seg of segmentList) {
        segmentLookup.set(`${seg.startPointId}->${seg.endPointId}`, seg);
      }

      if (points.length > 0) {
        distanceByPointId.set(points[0].id, cumulativeDistKm);

        for (let i = 0; i < points.length - 1; i++) {
          const startPoint = points[i];
          const endPoint = points[i + 1];
          const linkingSegment = segmentLookup.get(`${startPoint.id}->${endPoint.id}`);

          cumulativeDistKm += getSegmentDistanceKm(linkingSegment, startPoint, endPoint);
          distanceByPointId.set(endPoint.id, cumulativeDistKm);
        }

        if (sectionIdx < sections.length - 1) {
          const nextSectionFirstPoint = sections[sectionIdx + 1]?.points?.[0];
          const lastPoint = points[points.length - 1];

          if (lastPoint && nextSectionFirstPoint) {
            // Find connector: segment starting from lastPoint going outside this section
            let connectorSegment;
            for (const seg of segmentList) {
              if (seg.startPointId === lastPoint.id && !pointIdSet.has(seg.endPointId)) {
                connectorSegment = seg;
                break;
              }
            }
            cumulativeDistKm += getSegmentDistanceKm(connectorSegment, lastPoint, nextSectionFirstPoint);
          }
        }
      }

      return {
        ...section,
        points: points.map((point) => ({
          ...point,
          dist_km: Number((distanceByPointId.get(point.id) ?? cumulativeDistKm).toFixed(6))
        }))
      };
    });
  }, [sections]);

  const handleOpenExportModal = () => {
    const hasSections = previewRoute ? previewRoute.sections.length > 0 : sections.some(s => s.points.length > 0);
    if (!hasSections) return;
    setIsExportModalOpen(true);
  };

  const MOBILE_PREVIEW_PANEL_ESTIMATED_H = 220; // rough estimate for step-1 fitBounds

  const fitMapToSections = useCallback((sectionsToFit, customPadding = null) => {
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
                { padding: customPadding ?? 100, duration: 1000 }
            );
        } catch (e) {
            console.error("Fit bounds error:", e);
        }
    }
  }, []);

  const handlePreviewRoute = async (routeId) => {
    setIsLoading(true);
    setLoadingMsg('Loading Preview...');

    const isMobile = window.innerWidth < 768;
    // Mobile UX: Close sidebar immediately to show map
    if (isMobile) {
        setIsSearchOpen(false);
        setIsMenuOpen(false);
    }

    // Mobile: step-1 padding uses estimated panel height so route lands in upper map area
    const previewPadding = isMobile
        ? { top: 60, bottom: MOBILE_PREVIEW_PANEL_ESTIMATED_H + 30, left: 40, right: 40 }
        : null;

    try {
        const headers = {};
        if (auth.currentUser) {
            const idToken = await auth.currentUser.getIdToken();
            headers['Authorization'] = `Bearer ${idToken}`;
        }
        const res = await fetch(`/api/routes/${routeId}`, { headers });
        if (!res.ok) throw new Error("Failed to load route data");
        const data = await res.json();
        analytics.routeViewed(routeId, data.distance);
        posthog.capture('route_viewed', { route_id: routeId, distance: data.distance, title: data.title });

        if (data.editor_state && data.editor_state.sections) {
             // 에디터로 저장된 루트: editor_state.sections 사용
             setPreviewRoute({
                 id: data.route_id,
                 data: data,
                 sections: data.editor_state.sections
             });
             fitMapToSections(data.editor_state.sections, previewPadding);
        } else if (data.points && Array.isArray(data.points.lat) && data.points.lat.length >= 2) {
             // v1.0 columnar 포맷 (GPX 임포트 스크립트로 저장된 루트)
             const lats = data.points.lat;
             const lons = data.points.lon;
             const eles = data.points.ele || lats.map(() => 0);
             const coords = lats.map((lat, i) => [lons[i], lat, eles[i]]);

             const surfColors = { 1: '#2979FF', 2: '#2979FF', 3: '#9E9E9E', 4: '#FFC400', 5: '#00E676', 6: '#8D6E63', 7: '#8D6E63', 0: '#9E9E9E' };
             const segs = data.segments || {};
             const displayFeatures = (segs.p_start || []).map((sIdx, i) => ({
                 type: 'Feature',
                 geometry: { type: 'LineString', coordinates: coords.slice(sIdx, (segs.p_end[i] || sIdx) + 1) },
                 properties: { color: surfColors[segs.surf_id?.[i]] ?? '#9E9E9E', start_index: sIdx, end_index: segs.p_end?.[i] }
             }));

             const startPt = { id: generateId(), lng: coords[0][0], lat: coords[0][1], type: 'via', name: 'Start' };
             const endPt   = { id: generateId(), lng: coords[coords.length - 1][0], lat: coords[coords.length - 1][1], type: 'via', name: 'End' };
             const syntheticSections = [{
                 id: generateId(),
                 name: 'Route',
                 points: [startPt, endPt],
                 segments: [{
                     id: generateId(),
                     startPointId: startPt.id,
                     endPointId: endPt.id,
                     geometry: { type: 'LineString', coordinates: coords },
                     distance: (data.distance || 0) / 1000,
                     ascent: data.elevation_gain || 0,
                     type: 'api',
                     surfaceSegments: displayFeatures
                 }],
                 color: SECTION_COLORS[0]
             }];

             setPreviewRoute({ id: data.route_id, data: data, sections: syntheticSections });
             fitMapToSections(syntheticSections, previewPadding);
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
     const sectionsToLoad = previewRoute.sections;

     setSections(sectionsToLoad);
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

     // Exit nearby mode if active
     if (isNearbyMode) {
         if (nearbyDebounceRef.current) clearTimeout(nearbyDebounceRef.current);
         setIsNearbyMode(false);
         setNearbyRoutes(null);
         setNearbyCenter(null);
     }

     // Clear preview state
     setPreviewRoute(null);
     setMobilePreviewExpanded(false);
     setIsElevationChartVisible(true);

     // Wait for panel close + elevation chart open animations (~300ms) then fit
     setTimeout(() => {
         const isMobile = window.innerWidth < 768;
         fitMapToSections(sectionsToLoad, {
             top: 80,
             bottom: 80,
             left: isMobile ? 40 : 80,
             right: isMobile ? 40 : 80,
         });
     }, 350);
  };

  const copyShareLink = () => {
      const identifier = previewRoute
          ? (previewRoute.data.uuid || previewRoute.data.route_id)
          : ((routeStatus === 'LINK_ONLY' && routeUuid) ? routeUuid : currentRouteId);
      if (!identifier) return;
      const shareUrl = `${window.location.origin}/route/${identifier}`;
      navigator.clipboard.writeText(shareUrl).then(() => {
          setPreviewLinkCopied(true);
          setTimeout(() => setPreviewLinkCopied(false), 2000);
      }).catch(() => {
          alert('Failed to copy link.');
      });
  };

  const cancelPreview = (options = {}) => {
      const { reopenSearchOnMobile = true } = options;
      setPreviewRoute(null);
      setMobilePreviewExpanded(false);
      setPreviewLinkCopied(false);
      setIsElevationChartVisible(true);
      if (sections.some(s => s.points.length > 0)) {
          fitMapToSections(sections);
      }
      if (reopenSearchOnMobile && window.innerWidth < 768) {
          setIsSearchOpen(true);
      }
  };

  const performExport = async (filename, format) => {
    const sourceSections = previewRoute ? previewRoute.sections : sectionsWithPointDistances;
    const sourceRouteId = previewRoute ? previewRoute.data.route_id : currentRouteId;
    if (!sourceSections || sourceSections.length === 0) return;

    try {
        // Deep clone sections to remove any potential non-serializable properties
        const cleanSections = sourceSections.map(sec => ({
            id: sec.id,
            name: sec.name,
            color: sec.color,
            points: sec.points.map(p => ({
                id: p.id,
                lat: p.lat,
                lng: p.lng,
                type: p.type,
                name: p.name,
                dist_km: p.dist_km
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

        
        analytics.routeExported(format);
        posthog.capture('route_exported', { format });
        const url = window.URL.createObjectURL(blob);

        const contentDisposition = null;
        let downloadFilename;
        if (contentDisposition) {
            // RFC 5987: filename*=UTF-8''encoded_name
            const starMatch = contentDisposition.match(/filename\*=UTF-8''(.+)/i);
            if (starMatch) {
                downloadFilename = decodeURIComponent(starMatch[1]);
            } else {
                const plainMatch = contentDisposition.match(/filename="?([^"]+)"?/);
                if (plainMatch) downloadFilename = plainMatch[1];
            }
        }
        if (!downloadFilename) {
            const safeName = (filename || 'route').replace(/[^a-z0-9가-힣]/gi, '_');
            downloadFilename = `${safeName}.${format}`;
        }

        const a = document.createElement('a');
        a.href = url;
        a.download = downloadFilename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        if (sourceRouteId) {
            fetch(`/api/routes/${sourceRouteId}/download`, { method: 'POST' }).catch(() => {});
        }

    } catch (e) {
        console.error(`${format.toUpperCase()} Export Error:`, e);
        alert(`Failed to download ${format.toUpperCase()}: ${e.message}`);
    }
  };

  const handleSectionDownload = async (sectionIdx, format = 'gpx') => {
    const section = sectionsWithPointDistances[sectionIdx];
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
        let filename;
        if (contentDisposition) {
            const starMatch = contentDisposition.match(/filename\*=UTF-8''(.+)/i);
            if (starMatch) {
                filename = decodeURIComponent(starMatch[1]);
            } else {
                const plainMatch = contentDisposition.match(/filename="?([^"]+)"?/);
                if (plainMatch) filename = plainMatch[1];
            }
        }
        if (!filename) {
            const safeName = (section.name || 'section').replace(/[^a-z0-9가-힣]/gi, '_');
            filename = `${safeName}.${format}`;
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
    const routeFeatures = features ? features.filter(f => f.layer.id === 'route-layer') : [];
    const waypointFeature = features ? features.find(f => f.layer.id === 'admin-waypoints-layer') : null;

    if (routeFeatures.length > 0 && lngLat && Number.isFinite(lngLat.lng) && Number.isFinite(lngLat.lat)) {
      setMapHoverCoord({ lng: lngLat.lng, lat: lngLat.lat });
    } else {
      setMapHoverCoord(null);
    }
    
    // 1. Surface Info Tooltip or Waypoint Tooltip
    if (waypointFeature) {
        setHoverInfo({ 
            isWaypoint: true,
            feature: waypointFeature, 
            x, y 
        });
    } else if (hoveredFeature && hoveredFeature.properties.surface) {
        setHoverInfo({ 
            isWaypoint: false,
            feature: hoveredFeature, 
            x, y 
        });
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
      future: [structuredClone(sections), ...curr.future] 
    }));
    setSections(prev);
  };

  const handleRedo = () => {
    if (history.future.length === 0) return;
    const next = history.future[0];
    setHistory(curr => ({ 
      past: [...curr.past, structuredClone(sections)], 
      future: curr.future.slice(1) 
    }));
    setSections(next);
  };

  const saveToHistory = (currentSections) => {
    setIsDirty(true);
    setSectionsVersion(v => v + 1);
    setHistory(curr => ({
      past: [...curr.past, structuredClone(currentSections)],
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

    // Check for Nearby Route Click (ALWAYS check this first if layer exists)
    if (e.features) {
        const nearbyFeature = e.features.find(f => f.layer.id === 'nearby-routes-layer');
        if (nearbyFeature) {
            handlePreviewRoute(nearbyFeature.properties.id);
            return;
        }
    }

    // Waypoint click — open detail modal instead of creating a point
    if (isWaypointMode && e.features) {
        const wpFeature = e.features.find(f => f.layer.id === 'admin-waypoints-layer');
        if (wpFeature) {
            setSelectedWaypointId(wpFeature.properties.id);
            analytics.waypointViewed(wpFeature.properties.id, wpFeature.properties.type);
            posthog.capture('waypoint_viewed', { waypoint_id: wpFeature.properties.id, waypoint_type: wpFeature.properties.type });
            return;
        }
    }

    // If Nearby Mode is ON, DO NOT create points. Just return.
    if (isNearbyMode) {
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

    // If a point is currently focused from the sidebar, first map click cancels focus.
    // This click should not create a new route point.
    if (focusedPointId) {
      setFocusedPointId(null);
      setHoveredCoord(null);
      setHoveredSectionIndex(null);
      return;
    }

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
    
    let updatedSections = structuredClone(sections); // Deep copy to avoid mutation issues
    const targetSection = updatedSections[sectionIdx];
    const targetPoint = targetSection.points[pointIdx];

    if (targetPoint?.id && targetPoint.id === focusedPointId) {
      setFocusedPointId(null);
      setHoveredCoord(null);
    }
    
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
                    const latest = structuredClone(prev);
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
      let updatedSections = structuredClone(sections);
      
      const segmentsToFetch = deleteSection(sectionIdx, updatedSections);
      
      setSections(updatedSections);
      
      if (segmentsToFetch.length > 0) {
        setIsLoading(true);
        try {
            await Promise.all(segmentsToFetch.map(async ({ sectionIdx: sIdx, segmentId, start, end }) => {
                const realData = await fetchSegmentData(start, end, isMockMode ? 'mock' : 'real');
                setSections(prev => {
                    const latest = structuredClone(prev);
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
      
      let updatedSections = structuredClone(sections);
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

  const handlePointTypeChange = (sectionIdx, pointIdx, newType) => {
      saveToHistory(sections);
      const updatedSections = [...sections];
      updatedSections[sectionIdx].points[pointIdx].type = newType;
      setSections(updatedSections);
  };

  const handlePointMove = async (sectionIdx, pointIdx, evt) => {
    const { lng, lat } = evt.lngLat;
    saveToHistory(sections);

    let updatedSections = structuredClone(sections);
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
                    const latest = structuredClone(prev);
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
    const updatedSections = structuredClone(sections);
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

  const totalDist = useMemo(() => sections.reduce((acc, sec) => acc + sec.segments.reduce((sAcc, s) => sAcc + (s.distance || 0), 0), 0), [sections]);
  const totalAscent = useMemo(() => sections.reduce((acc, sec) => acc + sec.segments.reduce((sAcc, s) => sAcc + (s.ascent || 0), 0), 0), [sections]);

  const surfaceGeoJSON = useMemo(() => ({
    type: 'FeatureCollection',
    features: sections.flatMap((sec, secIdx) => sec.segments.flatMap((s, segIdx) => {
        const props = {
            color: sec.color,
            sectionIndex: secIdx,
            segmentIndex: segIdx,
            sectionColor: sec.color
        };

        if (s.type === 'mock') props.color = '#FFA726';
        else if (s.type === 'loading') props.color = '#9E9E9E';
        else if (s.type === 'error') props.color = '#F44336';

        if (s.surfaceSegments && s.surfaceSegments.length > 0) {
            return s.surfaceSegments.map(fs => ({
                ...fs,
                properties: {
                    ...props,
                    ...fs.properties,
                    sectionColor: sec.color
                }
            }));
        }
        return [{ type: 'Feature', geometry: s.geometry, properties: props }];
    }))
  }), [sections]);

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

  // Mobile re-fit: on new preview load (120ms) or panel expand/collapse (400ms for animations)
  React.useEffect(() => {
      if (!previewRoute || window.innerWidth >= 768) return;
      const delay = mobilePreviewExpanded ? 400 : 120;
      const timer = setTimeout(() => {
          const h = previewPanelMobileRef.current?.offsetHeight ?? MOBILE_PREVIEW_PANEL_ESTIMATED_H;
          fitMapToSections(previewRoute.sections, { top: 60, bottom: h + 30, left: 40, right: 40 });
      }, delay);
      return () => clearTimeout(timer);
  }, [previewRoute, mobilePreviewExpanded, fitMapToSections]);


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
                  sections: sectionsWithPointDistances
              }
          };

          if (modalData.isOverwrite && currentRouteId) {
             payload.route_id = currentRouteId;
          }

          const result = await apiClient.post('/api/routes', payload);
          console.log('[Save] response:', result, 'route_id:', result.route_id, 'uuid:', result.uuid);
          analytics.routeCreated(result.route_id, result.distance, result.elevation_gain, modalData.tags?.length || 0);
          posthog.capture('route_created', { route_id: result.route_id, distance: result.distance, elevation_gain: result.elevation_gain, tags: modalData.tags, is_overwrite: modalData.isOverwrite });
          alert(modalData.isOverwrite ? "Route updated!" : "Route saved successfully!");
          
          // Update local state with saved metadata
          setCurrentRouteId(result.route_id);
          setRouteUuid(result.uuid || null);
          setRouteName(modalData.title);
          setRouteDescription(modalData.description);
          setRouteStatus(modalData.status);
          setRouteTags(modalData.tags);
          setRouteOwnerId(auth.currentUser.uid); // Assuming current user is now owner
          setIsDirty(false); // Changes saved
          setIsMenuOpen(false);
          setIsSearchOpen(false);
          setSearchRefreshTrigger(prev => prev + 1);

          // If nearby mode was pending after save, activate it now
          if (pendingNearbyAfterSaveRef.current) {
              pendingNearbyAfterSaveRef.current = false;
              resetRoute();
              setIsNearbyMode(true);
              fetchNearbyRoutes();
          }
      } catch (e) {
          console.error(e);
          alert(`Error saving route: ${e.message}`);
      } finally {
          setIsLoading(false);
          setLoadingMsg('');
      }
  };

  const handleImportGPX = async (file) => {
      setIsLoading(true);
      setLoadingMsg('Importing GPX...');
      try {
          const formData = new FormData();
          formData.append('file', file);

          // Use apiClient with formData (don't stringify, don't override content-type)
          const data = await apiClient.post('/api/routes/import', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
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
                          type: wpt.type,
                          name: wpt.name,
                          ...(wpt.dist_km != null ? { dist_km: wpt.dist_km } : {})
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
          setRouteUuid(null);
          setRouteName('Imported GPX');
          setRouteDescription('');
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
          
          let loadedSections = null;

          if (data.editor_state && data.editor_state.sections) {
              loadedSections = data.editor_state.sections;
          } else if (data.points && Array.isArray(data.points.lat) && data.points.lat.length >= 2) {
              // v1.0 columnar format fallback (imported routes without editor_state)
              const lats = data.points.lat;
              const lons = data.points.lon;
              const eles = data.points.ele || lats.map(() => 0);
              const coords = lats.map((lat, i) => [lons[i], lat, eles[i]]);

              const surfColors = { 1: '#2979FF', 2: '#2979FF', 3: '#9E9E9E', 4: '#FFC400', 5: '#00E676', 6: '#8D6E63', 7: '#8D6E63', 0: '#9E9E9E' };
              const segs = data.segments || {};
              const displayFeatures = (segs.p_start || []).map((sIdx, i) => ({
                  type: 'Feature',
                  geometry: { type: 'LineString', coordinates: coords.slice(sIdx, (segs.p_end[i] || sIdx) + 1) },
                  properties: { color: surfColors[segs.surf_id?.[i]] ?? '#9E9E9E', start_index: sIdx, end_index: segs.p_end?.[i] }
              }));

              const startPt = { id: generateId(), lng: coords[0][0], lat: coords[0][1], type: 'via', name: 'Start' };
              const endPt   = { id: generateId(), lng: coords[coords.length - 1][0], lat: coords[coords.length - 1][1], type: 'via', name: 'End' };
              loadedSections = [{
                  id: generateId(),
                  name: 'Route',
                  points: [startPt, endPt],
                  segments: [{
                      id: generateId(),
                      startPointId: startPt.id,
                      endPointId: endPt.id,
                      geometry: { type: 'LineString', coordinates: coords },
                      distance: (data.distance || 0) / 1000,
                      ascent: data.elevation_gain || 0,
                      type: 'api',
                      surfaceSegments: displayFeatures
                  }],
                  color: SECTION_COLORS[0]
              }];
          }

          if (loadedSections) {
              setSections(loadedSections);

              // Update all metadata to enable Correct Fork/Overwrite behavior
              setCurrentRouteId(data.route_id);
              setRouteUuid(data.uuid || null);
              setRouteName(data.title || '');
              setRouteDescription(data.description || '');
              setRouteStatus(data.status || 'PUBLIC');
              setRouteTags(data.tags || []);
              setRouteOwnerId(data.owner_id);
              setRouteStats(data.stats || { views: 0, downloads: 0 });

              setHistory({ past: [], future: [] });
              setIsDirty(false);
              setIsMenuOpen(false);
              setIsSearchOpen(false);

              fitMapToSections(loadedSections);

              if (!skipConfirm) alert("Route loaded!");
          } else {
              alert("Invalid route data: no editor state or points data found.");
          }

      } catch (e) {
          console.error(e);
          alert(`Error loading route: ${e.message}`);
      } finally {
          setIsLoading(false);
          setLoadingMsg('');
      }
  };

  // Auto-load route from URL (preview mode)
  React.useEffect(() => {
    if (initialRouteId) {
      handlePreviewRoute(initialRouteId);
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

  const resetRoute = () => {
    setSections([{ id: generateId(), name: 'Section 1', points: [], segments: [], color: SECTION_COLORS[0] }]);
    setRouteName('');
    setRouteDescription('');
    setRouteStatus('PUBLIC');
    setRouteTags([]);
    setCurrentRouteId(null);
    setRouteUuid(null);
    setRouteOwnerId(null);
    setHistory({ past: [], future: [] });
    setIsDirty(false);
    setIsMenuOpen(false);
    setIsSearchOpen(false);
  };

  const handleNewRoute = () => {
    if (sections.some(s => s.points.length > 0)) {
        if (!confirm("Your unsaved changes will be lost. Create a new route?")) return;
    }
    // Exit nearby mode if active
    if (isNearbyMode) {
        if (nearbyDebounceRef.current) clearTimeout(nearbyDebounceRef.current);
        setIsNearbyMode(false);
        setNearbyRoutes(null);
        setNearbyCenter(null);
    }
    setPreviewRoute(null);
    setMobilePreviewExpanded(false);
    resetRoute();
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
        isNearbyMode={isNearbyMode}
        onToggleNearby={toggleNearby}
        isWaypointMode={isWaypointMode}
        onToggleWaypoint={toggleWaypointMode}
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
                    routeUuid={routeUuid}
                    routeStatus={routeStatus}
                    routeStats={routeStats}
                    history={history}
                    onUndo={handleUndo}
                    onRedo={handleRedo}
                    onClear={() => { saveToHistory(sections); setSections([{ id: generateId(), name: 'Section 1', points: [], segments: [], color: SECTION_COLORS[0] }]); }}
                    onSave={openSaveModal}
                    onDownloadGPX={handleOpenExportModal}
                    sections={sections}
                    focusedPointId={focusedPointId}
                    onPointFocus={handleMenuPointFocus}
                    onPointRemove={handlePointRemove}
                    onPointRename={handlePointRename}
                    onSplitSection={handleSplitSection}
                    onSectionHover={handleSectionHover}
                    onSectionDelete={handleSectionDelete}
                    onSectionMerge={handleSectionMerge}
                    onSectionRename={handleSectionRename}
                    onSectionDownload={handleSectionDownload}
                    onPointTypeChange={handlePointTypeChange}
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
                 <SearchPanel
                     onLoadRoute={handlePreviewRoute}
                     activePreviewId={previewRoute?.id ?? null}
                     routeFilters={routeFilters}
                     onFiltersChange={(filters) => {
                         setRouteFilters(filters);
                         routeFiltersRef.current = filters;
                     }}
                     refreshTrigger={searchRefreshTrigger}
                 />
             </div>
        </div>

        {/* Waypoint Panel */}
        <div className={`
            ${isWaypointMode ? 'w-80 border-r border-gray-800 pointer-events-auto shadow-2xl' : 'w-0'}
            h-full bg-gray-900 overflow-hidden transition-all duration-300 ease-in-out
        `}>
             <div className="w-80 h-full"> {/* Inner Fixed Width Container */}
                 {isWaypointMode && (
                     <WaypointPanel
                         onWaypointClick={(wp) => {
                             setSelectedWaypointId(wp.id);
                             flyMapToPoint({ lng: wp.lng, lat: wp.lat });
                         }}
                         onWaypointAdd={(wp) => {
                             const e = { lngLat: { lng: wp.lng, lat: wp.lat } };
                             handleMapClick({ ...e, originalEvent: { target: document.createElement('div') } });
                         }}
                         onClose={toggleWaypointMode}
                     />
                 )}
             </div>
        </div>
        {/* Desktop Preview Detail Panel (md+) - slides in next to search panel */}
        <div className={`
            hidden md:block
            ${previewRoute ? 'w-80 border-r border-gray-800 pointer-events-auto' : 'w-0'}
            h-full bg-gray-900 overflow-hidden transition-all duration-300 ease-in-out flex-shrink-0
        `}>
            {previewRoute && (
            <div className="w-80 h-full flex flex-col">
                {/* Fixed: Title + X + meta info */}
                <div className="px-4 pt-4 pb-3 flex flex-col gap-3 shrink-0 border-b border-gray-800">
                    {/* Number + Title + X */}
                    <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                            {previewRoute.data.route_num && (
                                <button
                                    onClick={copyShareLink}
                                    className={`text-[11px] font-mono transition-colors cursor-pointer hover:text-riduck-primary ${previewLinkCopied ? 'text-green-400' : 'text-gray-500'}`}
                                    title={previewLinkCopied ? 'Copied!' : 'Copy share link'}
                                >
                                    {previewLinkCopied ? 'Copied!' : `#${previewRoute.data.route_num}`}
                                </button>
                            )}
                            <h2 className="text-white font-bold text-base leading-snug mt-0.5">{previewRoute.data.title || 'Untitled Route'}</h2>
                        </div>
                        <button
                            onClick={() => cancelPreview()}
                            className="text-gray-500 hover:text-white transition-colors p-1 rounded-lg hover:bg-gray-800 shrink-0 mt-0.5"
                            title="Close preview"
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/></svg>
                        </button>
                    </div>

                    {/* Author + Date */}
                    <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                            {previewRoute.data.author_image
                                ? <img src={previewRoute.data.author_image} alt="" className="w-6 h-6 rounded-full object-cover shrink-0" />
                                : <div className="w-6 h-6 rounded-full bg-gray-700 flex items-center justify-center shrink-0">
                                    <svg className="w-3.5 h-3.5 text-gray-400" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clipRule="evenodd"/></svg>
                                  </div>
                            }
                            <span className="text-sm text-gray-300 font-medium truncate">{previewRoute.data.author_name || '—'}</span>
                        </div>
                        <div className="text-right text-[11px] text-gray-500 font-mono shrink-0">
                            {previewRoute.data.created_at && <div>{formatDate(previewRoute.data.created_at)}</div>}
                            {previewRoute.data.updated_at && previewRoute.data.updated_at !== previewRoute.data.created_at && (
                                <div className="text-[10px]">ed. {formatDate(previewRoute.data.updated_at)}</div>
                            )}
                        </div>
                    </div>

                    {/* Tags */}
                    {previewRoute.data.tags?.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                            {previewRoute.data.tags.map(tag => (
                                <span key={tag} className="bg-gray-800 text-gray-300 text-[11px] px-2 py-0.5 rounded-full border border-gray-700">{tag}</span>
                            ))}
                        </div>
                    )}

                    {/* Stats */}
                    <div className="grid grid-cols-2 gap-2">
                        <div className="bg-gray-800/60 rounded-xl px-3 py-2.5">
                            <div className="text-[10px] text-gray-500 font-medium mb-0.5">Distance</div>
                            <div className="text-white font-bold text-sm font-mono">{previewDistKm.toFixed(1)}<span className="text-xs text-gray-400 font-normal ml-0.5">km</span></div>
                        </div>
                        <div className="bg-gray-800/60 rounded-xl px-3 py-2.5">
                            <div className="text-[10px] text-gray-500 font-medium mb-0.5">Elevation</div>
                            <div className="text-white font-bold text-sm font-mono">+{Math.round(previewAscentM)}<span className="text-xs text-gray-400 font-normal ml-0.5">m</span></div>
                        </div>
                    </div>

                    {/* View/Download counts + Export button */}
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4 text-xs text-gray-500">
                            {(previewRoute.data.stats?.views > 0 || previewRoute.data.stats?.downloads > 0) && (<>
                                <span className="flex items-center gap-1">
                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                                    {previewRoute.data.stats.views.toLocaleString()}
                                </span>
                                <span className="flex items-center gap-1">
                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
                                    {previewRoute.data.stats.downloads.toLocaleString()}
                                </span>
                            </>)}
                        </div>
                        <div className="flex items-center gap-1">
                            <button
                                onClick={copyShareLink}
                                className={`flex items-center gap-1 text-xs transition-colors px-2 py-1 rounded-lg hover:bg-gray-800 ${previewLinkCopied ? 'text-green-400' : 'text-gray-400 hover:text-riduck-primary'}`}
                                title={previewLinkCopied ? 'Copied!' : 'Copy share link'}
                            >
                                {previewLinkCopied ? (
                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7"/></svg>
                                ) : (
                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/></svg>
                                )}
                            </button>
                            <button
                                onClick={handleOpenExportModal}
                                className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-riduck-primary transition-colors px-2 py-1 rounded-lg hover:bg-gray-800"
                                title="Export GPX/TCX"
                            >
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
                                GPX/TCX
                            </button>
                        </div>
                    </div>
                </div>

                {/* Scrollable: Description only */}
                {previewRoute.data.description ? (
                    <div className="flex-1 overflow-y-auto custom-scrollbar px-4 py-3">
                        <div className="prose prose-sm prose-invert max-w-none">
                            <ReactMarkdown>{previewRoute.data.description}</ReactMarkdown>
                        </div>
                    </div>
                ) : (
                    <div className="flex-1" />
                )}

                {/* Action Buttons */}
                <div className="px-4 pb-4 pt-2 shrink-0 border-t border-gray-800 grid grid-cols-2 gap-3">
                    <button
                        onClick={() => cancelPreview()}
                        className="py-2.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 font-bold text-sm transition-all active:scale-[0.98]"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={confirmPreviewLoad}
                        className="py-2.5 rounded-xl bg-riduck-primary hover:bg-riduck-primary/90 text-white font-bold text-sm shadow-lg shadow-riduck-primary/20 transition-all active:scale-[0.98] flex items-center justify-center gap-1.5"
                    >
                        Load Route
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7"/></svg>
                    </button>
                </div>
            </div>
            )}
        </div>
      </div>

      {/* 3. Main Content (Right) - Map & Chart */}
      <div className="flex-1 flex flex-col relative h-full min-w-0">
        {isLoading && <div className="absolute inset-0 z-[9999] bg-black/30 backdrop-blur-[2px] flex flex-col items-center justify-center"><div className="animate-spin rounded-full h-12 w-12 border-b-4 border-riduck-primary mb-4"></div><div className="text-white font-bold text-lg animate-pulse">{loadingMsg}</div></div>}
        
        {/* Map Area */}
        <div className="flex-1 relative">
                        {/* Top Right: Tools Container */}
            <div className={`absolute top-4 right-4 md:top-6 md:right-6 z-10 flex-col items-end gap-3 pointer-events-none ${mobilePreviewExpanded ? 'hidden md:flex' : 'flex'}`}>
                {/* 1. Straight Line Mode Toggle */}
                {!isNearbyMode && <button
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
                </button>}

                {/* 2. Share + Place Search Bar (Floating) */}
                <div className="pointer-events-auto relative flex items-center gap-2">
                    {/* Share Link */}
                    {(previewRoute || currentRouteId) && !isPlaceSearchOpen && (
                        <button
                            onClick={copyShareLink}
                            className={`flex items-center justify-center w-10 h-10 md:w-12 md:h-12 rounded-full shadow-xl backdrop-blur-md transition-all active:scale-95 ${
                                previewLinkCopied
                                    ? 'bg-green-500/90 text-white border border-green-500'
                                    : 'bg-gray-900/90 border border-gray-700 text-gray-400 hover:text-white hover:border-gray-500'
                            }`}
                            title={previewLinkCopied ? 'Copied!' : 'Copy share link'}
                        >
                            {previewLinkCopied ? (
                                <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7"/></svg>
                            ) : (
                                <svg className="w-4 h-4 md:w-5 md:h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/></svg>
                            )}
                        </button>
                    )}
                    {/* Search */}
                    <div className={`flex items-center bg-gray-900/90 backdrop-blur-md border border-gray-700 shadow-xl rounded-full transition-all duration-300 ease-in-out h-10 md:h-12 overflow-hidden ${isPlaceSearchOpen ? 'w-64 md:w-80 px-4' : 'w-10 md:w-12 justify-center'}`}>

                        {/* Input Field (Visible only when open) */}
                        <input
                            type="text"
                            placeholder="장소 검색 또는 좌표 입력"
                            value={placeSearchQuery}
                            onChange={(e) => handlePlaceSearchInput(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                    if (placeSearchTimerRef.current) clearTimeout(placeSearchTimerRef.current);
                                    performPlaceSearch(placeSearchQuery);
                                }
                            }}
                            className={`bg-transparent text-white text-sm outline-none transition-all duration-300 h-full placeholder-gray-500 ${isPlaceSearchOpen ? 'flex-1 opacity-100' : 'w-0 opacity-0'}`}
                        />

                        {/* Loading Spinner */}
                        {placeSearchLoading && isPlaceSearchOpen && (
                            <div className="ml-1 shrink-0">
                                <div className="w-4 h-4 border-2 border-gray-500 border-t-white rounded-full animate-spin" />
                            </div>
                        )}

                        {/* Toggle Button (Magnifying Glass / Close) */}
                        <button
                            onClick={() => {
                                if (!isPlaceSearchOpen) {
                                    setIsPlaceSearchOpen(true);
                                } else {
                                    closePlaceSearch();
                                }
                            }}
                            className={`text-gray-400 hover:text-white transition-colors shrink-0 flex items-center justify-center ${isPlaceSearchOpen ? 'ml-2' : ''}`}
                        >
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 md:h-6 md:w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={isPlaceSearchOpen && placeSearchQuery ? "M6 18L18 6M6 6l12 12" : "M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"} />
                            </svg>
                        </button>
                    </div>

                    {/* Search Results Dropdown */}
                    {isPlaceSearchOpen && placeSearchResults.length > 0 && (
                        <div className="absolute top-full mt-2 left-0 right-0 bg-gray-900/95 backdrop-blur-md border border-gray-700 rounded-xl shadow-2xl overflow-hidden z-50">
                            {placeSearchResults.map((result, idx) => (
                                <button
                                    key={idx}
                                    onClick={() => handlePlaceSelect(result)}
                                    className="w-full text-left px-4 py-3 hover:bg-gray-700/50 transition-colors border-b border-gray-800 last:border-b-0"
                                >
                                    <div className="text-white text-sm font-medium truncate">{result.name}</div>
                                    <div className="text-gray-400 text-xs truncate mt-0.5">{result.address}</div>
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Stats Overlay / Nearby Mode Badge */}
            {isNearbyMode ? (
                <div className="absolute top-4 left-4 md:top-6 md:left-6 z-10 flex items-center gap-2">
                    <button
                        onClick={() => setIsNearbyFilterOpen(true)}
                        className="relative backdrop-blur-md bg-blue-500/15 border border-blue-400/40 px-4 py-2 md:px-6 md:py-3 rounded-2xl shadow-2xl cursor-pointer hover:bg-blue-500/25 transition-colors text-left"
                    >
                        {(routeFilters.minDistance !== '' || routeFilters.maxDistance !== '' ||
                          routeFilters.minElevation !== '' || routeFilters.maxElevation !== '' ||
                          routeFilters.tags.length > 0 || routeFilters.limit !== 7) && (
                            <span className="absolute -top-1 -right-1 w-3 h-3 bg-blue-400 rounded-full border-2 border-gray-900" />
                        )}
                        <p className="text-[9px] md:text-[10px] text-blue-300 uppercase font-bold tracking-wider mb-0.5">탐색 모드</p>
                        <p className="text-sm md:text-base font-bold text-white leading-none">
                            반경 {nearbyCenter ? nearbyCenter.radiusKm : '—'}km
                            <span className="text-[10px] md:text-xs text-blue-300 font-normal ml-1.5">인기순 {routeFilters.limit}개</span>
                        </p>
                    </button>
                    <button
                        onClick={() => {
                            if (!navigator.geolocation) return;
                            navigator.geolocation.getCurrentPosition(
                                (pos) => {
                                    const { latitude, longitude } = pos.coords;
                                    const map = mapRef.current?.getMap ? mapRef.current.getMap() : mapRef.current;
                                    if (map) {
                                        map.flyTo({ center: [longitude, latitude], zoom: Math.max(map.getZoom(), 12), duration: 1000 });
                                    }
                                },
                                () => alert('위치 정보를 가져올 수 없습니다.')
                            );
                        }}
                        className="pointer-events-auto p-2.5 md:p-3 rounded-2xl backdrop-blur-md bg-blue-500/15 border border-blue-400/40 text-blue-300 hover:bg-blue-500/30 hover:text-white shadow-2xl transition-all"
                        title="내 위치로 이동"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 md:h-6 md:w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                    </button>
                </div>
            ) : (
                <div 
                    className={`absolute top-4 left-4 md:top-6 md:left-6 z-10 backdrop-blur-md px-5 py-2 md:px-8 md:py-3 rounded-2xl border shadow-2xl flex gap-4 md:gap-8 items-center transition-all duration-300 ${previewRoute ? 'bg-riduck-primary/15 border-riduck-primary/40 pointer-events-none' : isClean ? 'bg-gray-900/90 border-gray-700 pointer-events-none' : 'bg-gray-900/90 border-riduck-primary/50 shadow-[0_0_12px_rgba(42,158,146,0.25)] pointer-events-auto cursor-pointer hover:border-riduck-primary/80 hover:shadow-[0_0_18px_rgba(42,158,146,0.4)] hover:bg-gray-800/90 active:scale-[0.98]'}`}
                    onClick={!previewRoute ? openSaveModal : undefined}
                >
                    {previewRoute && (
                        <span className="text-riduck-primary text-[9px] md:text-[10px] font-bold uppercase tracking-wider absolute -top-2.5 left-3 bg-gray-900 px-1.5 rounded">Preview</span>
                    )}
                    <div className="text-center">
                        <p className="text-[8px] md:text-[10px] text-gray-400 uppercase font-bold tracking-wider">Distance</p>
                        <p className="text-lg md:text-2xl font-mono text-white font-bold">
                            {previewRoute ? previewDistKm.toFixed(1) : totalDist.toFixed(1)}
                            <span className="text-xs md:text-sm text-gray-500 ml-0.5 font-sans">km</span>
                        </p>
                    </div>
                    <div className="w-px h-6 md:h-8 bg-gray-700"></div>
                    <div className="text-center">
                        <p className="text-[8px] md:text-[10px] text-gray-400 uppercase font-bold tracking-wider">Ascent</p>
                        <p className="text-lg md:text-2xl font-mono text-white font-bold">
                            +{previewRoute ? Math.round(previewAscentM) : Math.round(totalAscent)}
                            <span className="text-xs md:text-sm text-gray-500 ml-0.5 font-sans">m</span>
                        </p>
                    </div>
                </div>
            )}

            {/* Mobile Only: Sidebar Toggles (Below Stats) */}
            <div className={`absolute top-[80px] left-4 z-10 gap-2 md:hidden ${mobilePreviewExpanded ? 'hidden' : 'flex'}`}>
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
                <button
                    onClick={toggleNearby}
                    className={`p-2.5 rounded-xl border shadow-xl backdrop-blur-md transition-all ${isNearbyMode ? 'bg-riduck-primary border-riduck-primary text-white shadow-riduck-primary/20' : 'bg-gray-900/90 border-gray-700 text-gray-400'}`}
                >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
                    </svg>
                </button>
                <div className="relative" ref={moreMenuRef}>
                    <button
                        onClick={() => setMoreMenuOpen(!moreMenuOpen)}
                        className={`p-2.5 rounded-xl border shadow-xl backdrop-blur-md transition-all ${moreMenuOpen ? 'bg-riduck-primary border-riduck-primary text-white shadow-riduck-primary/20' : 'bg-gray-900/90 border-gray-700 text-gray-400'}`}
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h.01M12 12h.01M19 12h.01M6 12a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0z" />
                        </svg>
                    </button>
                    {moreMenuOpen && (
                        <div className="absolute top-full mt-2 left-0 bg-gray-900/95 border border-gray-700 rounded-xl shadow-2xl backdrop-blur-md overflow-hidden animate-fade-in-up min-w-[160px]">
                            <button
                                onClick={() => { handleNewRoute(); setMoreMenuOpen(false); }}
                                disabled={isClean}
                                className={`w-full flex items-center gap-3 px-4 py-3 text-sm transition-all ${isClean ? 'text-gray-600 cursor-not-allowed' : 'text-gray-300 hover:bg-gray-800 hover:text-white'}`}
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                                </svg>
                                New Route
                            </button>
                            <label
                                className="w-full flex items-center gap-3 px-4 py-3 text-sm text-gray-300 hover:bg-gray-800 hover:text-white transition-all cursor-pointer"
                            >
                                <input type="file" accept=".gpx,.tcx" className="hidden" onChange={(e) => {
                                    const file = e.target.files[0];
                                    if (file) {
                                        handleImportGPX(file);
                                        e.target.value = '';
                                    }
                                    setMoreMenuOpen(false);
                                }} />
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                                </svg>
                                Import GPX/TCX
                            </label>
                            <button
                                onClick={() => { handleOpenExportModal(); setMoreMenuOpen(false); }}
                                disabled={isClean}
                                className={`w-full flex items-center gap-3 px-4 py-3 text-sm transition-all ${isClean ? 'text-gray-600 cursor-not-allowed' : 'text-gray-300 hover:bg-gray-800 hover:text-white'}`}
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                </svg>
                                Export GPX/TCX
                            </button>
                        </div>
                    )}
                </div>
            </div>

            <Map 
                ref={mapRef} 
                initialViewState={INITIAL_VIEW_STATE} 
                mapStyle="https://api.maptiler.com/maps/jp-mierune-dark/style.json?key=hmAnzLL30c4tItQZZ8B9" 
                onLoad={handleMapLoad}
                onClick={handleMapClick}
                onMouseMove={onHover}
                onMoveEnd={handleMapMoveEnd}
                
                onTouchStart={handleTouchStart}
                onTouchMove={handleTouchMove}
                onTouchEnd={handleTouchEnd}

                onMouseLeave={() => { setHoverInfo(null); setDragState(null); setMapHoverCoord(null); }} // Cancel drag if leave?
                interactiveLayerIds={['route-layer', 'nearby-routes-layer', 'admin-waypoints-layer']}
                style={{ width: '100%', height: '100%' }} 
                cursor={isLoading ? 'wait' : (dragState ? 'grabbing' : (insertCandidate ? 'grab' : (isNearbyMode ? 'default' : (hoverInfo?.isWaypoint ? 'pointer' : 'crosshair'))))}
            >
                {placeSearchPulse && (
                    <Marker longitude={placeSearchPulse.lon} latitude={placeSearchPulse.lat} anchor="center">
                        <div className="place-search-pulse" />
                    </Marker>
                )}

                {nearbyCenter && (
                    <>
                        <Source id="nearby-radius-source" type="geojson" data={makeCircleGeoJSON(nearbyCenter.lat, nearbyCenter.lng, nearbyCenter.radiusKm)}>
                            <Layer id="nearby-radius-fill" type="fill" paint={{ 'fill-color': '#60A5FA', 'fill-opacity': 0.06 }} />
                            <Layer id="nearby-radius-border" type="line" paint={{ 'line-color': '#60A5FA', 'line-width': 1.5, 'line-opacity': 0.5, 'line-dasharray': [4, 3] }} />
                        </Source>
                        <Marker longitude={nearbyCenter.lng} latitude={nearbyCenter.lat} anchor="center">
                            <div style={{ width: 12, height: 12, borderRadius: '50%', background: '#60A5FA', border: '2px solid white', boxShadow: '0 0 0 3px rgba(96,165,250,0.35)' }} />
                        </Marker>
                    </>
                )}

                {isNearbyMode && nearbyRoutes && (
                    <Source id="nearby-routes-source" type="geojson" data={nearbyRoutes}>
                        {/* 
                        <Layer
                            id="nearby-routes-layer"
                            type="line"
                            layout={{ 'line-join': 'round', 'line-cap': 'round' }}
                            paint={{
                                'line-color': ['get', 'zone_color'],
                                'line-width': 4,
                                'line-opacity': 0.85
                            }}
                        /> 
                        */}
                        <Layer
                            id="nearby-routes-layer-casing"
                            type="line"
                            layout={{ 'line-join': 'round', 'line-cap': 'round' }}
                            paint={{
                                'line-color': '#FFFFFF',
                                'line-width': previewRoute ? 5 : 6,
                                'line-opacity': previewRoute ? 0.15 : 0.6
                            }}
                        />
                        <Layer
                            id="nearby-routes-layer"
                            type="line"
                            layout={{ 'line-join': 'round', 'line-cap': 'round' }}
                            paint={{
                                'line-color': ['get', 'zone_color'],
                                'line-width': previewRoute ? 3 : 4,
                                'line-opacity': previewRoute ? 0.4 : 1.0
                            }}
                        />
                    </Source>
                )}

                {isWaypointMode && adminWaypointsGeoJSON && (
                    <Source id="admin-waypoints-source" type="geojson" data={adminWaypointsGeoJSON}>
                        <Layer 
                            id="admin-waypoints-layer" 
                            type="circle" 
                            paint={{
                                'circle-radius': ['step', ['get', 'tour_count'], 4, 2, 6, 5, 8],
                                'circle-color': ['step', ['get', 'tour_count'], '#377eb8', 2, '#ff7f00', 5, '#e41a1c'],
                                'circle-stroke-width': 2,
                                'circle-stroke-color': '#FFFFFF'
                            }} 
                        />
                    </Source>
                )}

                {surfaceGeoJSON.features.length > 0 && (
                    <Source id="route-source" type="geojson" data={surfaceGeoJSON}>
                        <Layer id="route-layer" type="line" layout={{ 'line-join': 'round', 'line-cap': 'round' }} paint={{
                            'line-color': hoveredSectionIndex !== null
                                ? ['case', ['==', ['get', 'sectionIndex'], hoveredSectionIndex], ['get', 'sectionColor'], ['get', 'color']]
                                : ['get', 'color'],
                            'line-width': hoveredSectionIndex !== null
                                ? ['case', ['==', ['get', 'sectionIndex'], hoveredSectionIndex], 8, 6]
                                : 6,
                            'line-opacity': 0.9
                        }} />
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

                {hoveredCoord && Number.isFinite(hoveredCoord.lng) && Number.isFinite(hoveredCoord.lat) && (
                    <Marker
                        longitude={hoveredCoord.lng}
                        latitude={hoveredCoord.lat}
                        anchor="center"
                        draggable={false}
                    >
                        <div className="pointer-events-none relative flex items-center justify-center">
                            <div className="absolute h-7 w-7 rounded-full border border-riduck-primary/40 bg-riduck-primary/10"></div>
                            <div className="h-3 w-3 rounded-full border-2 border-white bg-riduck-primary shadow-lg shadow-riduck-primary/40"></div>
                        </div>
                    </Marker>
                )}

                {sections.flatMap((sec, sIdx) => sec.points.map((p, pIdx, arr) => {
                    const isFirst = sIdx === 0 && pIdx === 0;
                    const isLast = sIdx === sections.length - 1 && pIdx === arr.length - 1;
                    const tier = getPointTier(p, isFirst, isLast);
                    const tierStyle = TIER_STYLES[tier];
                    const typeConfig = POINT_TYPE_CONFIG[p.type] || POINT_TYPE_CONFIG.via;
                    const IconComponent = typeConfig.icon;
                    const markerColor = isFirst ? '#10B981' : isLast ? '#EF4444'
                      : typeConfig.color || sec.color;

                    return (
                    <Marker
                        key={`${sec.id}-${p.id}`}
                        longitude={p.lng}
                        latitude={p.lat}
                        anchor="center"
                        draggable={true}
                        onDragEnd={(evt) => handlePointMove(sIdx, pIdx, evt)}
                    >
                    {(() => {
                      const isFocusedPoint = focusedPointId === p.id;
                      const showIcon = tier === 'large' && p.type !== 'via' && p.type !== 'section_start';
                      return (
                    <div
                      className={`group relative flex items-center justify-center ${tierStyle.map} rounded-full border-2 border-white cursor-pointer text-white font-black z-50 transition-transform ${
                        isFocusedPoint ? 'scale-125 shadow-[0_0_0_2px_rgba(42,158,146,0.35),0_0_14px_rgba(42,158,146,0.65)]' : 'shadow-lg hover:scale-110'
                      }`}
                      style={{ backgroundColor: markerColor }}
                      onClick={(e) => handlePointRemove(sIdx, pIdx, e)}
                    >
                        {isFocusedPoint && (
                          <span className="pointer-events-none absolute -inset-2 rounded-full border border-riduck-primary/60 animate-ping"></span>
                        )}
                        <span className="group-hover:hidden">
                          {showIcon ? <IconComponent size={14} strokeWidth={2.5} /> : pIdx + 1}
                        </span>
                        <span className="hidden group-hover:block">✕</span>
                    </div>
                      );
                    })()}
                    </Marker>
                    );
                }))}
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
                        {hoverInfo.isWaypoint ? (
                            <>
                                <div className="font-bold text-sm text-riduck-primary mb-1">
                                    {hoverInfo.feature.properties.name}
                                </div>
                                <div className="text-[11px] text-gray-300">
                                    {hoverInfo.feature.properties.description && (
                                        <div className="mb-1 text-gray-400 max-w-[200px] whitespace-normal">
                                            {hoverInfo.feature.properties.description}
                                        </div>
                                    )}
                                    <div>Type: {hoverInfo.feature.properties.type}</div>
                                    <div>Tours: {hoverInfo.feature.properties.tour_count}</div>
                                    {hoverInfo.feature.properties.has_images && <div>🖼️ Images available</div>}
                                    {hoverInfo.feature.properties.has_tips && <div>💡 Tips available</div>}
                                </div>
                            </>
                        ) : (
                            <>
                                <div className="flex items-center gap-2 mb-1">
                                    <div className="w-3 h-3 rounded-full shadow-sm" style={{backgroundColor: hoverInfo.feature.properties.color}}></div>
                                    <span className="font-bold text-sm">{hoverInfo.feature.properties.surface}</span>
                                </div>
                                {hoverInfo.feature.properties.description && (
                                    <div className="mt-1 text-[11px] text-gray-400 leading-tight max-w-[200px]">
                                        {hoverInfo.feature.properties.description}
                                    </div>
                                )}
                            </>
                        )}
                    </div>
                )}
            </Map>


            {/* Preview Control UI — Mobile only (floating bottom sheet) */}
            {previewRoute && (
                <div
                    ref={previewPanelMobileRef}
                    className="md:hidden absolute inset-x-0 bottom-0 z-30 pointer-events-auto animate-fadeInUp"
                    onClick={() => { setIsSearchOpen(false); setIsMenuOpen(false); }}
                >
                    <div className={`bg-gray-900/97 backdrop-blur-xl border-t border-gray-700/60 shadow-2xl rounded-t-2xl flex flex-col ${mobilePreviewExpanded ? 'max-h-[57vh] overflow-hidden' : ''}`}>
                        {/* Drag handle */}
                        <div className="w-8 h-1 bg-gray-700 rounded-full mx-auto absolute left-1/2 -translate-x-1/2 top-2" />

                        {/* Fixed info area */}
                        <div className="px-4 pt-4 pb-3 flex flex-col gap-3 shrink-0">
                            {/* Title + X */}
                            <div className="flex items-start justify-between gap-2">
                                <div className="min-w-0">
                                    {previewRoute.data.route_num && (
                                        <button
                                            onClick={(e) => { e.stopPropagation(); copyShareLink(); }}
                                            className={`text-[11px] font-mono transition-colors cursor-pointer hover:text-riduck-primary ${previewLinkCopied ? 'text-green-400' : 'text-gray-500'}`}
                                            title={previewLinkCopied ? 'Copied!' : 'Copy share link'}
                                        >
                                            {previewLinkCopied ? 'Copied!' : `#${previewRoute.data.route_num}`}
                                        </button>
                                    )}
                                    <h3 className="text-white font-bold text-base leading-snug">{previewRoute.data.title || 'Untitled Route'}</h3>
                                </div>
                                <button
                                    onClick={(e) => { e.stopPropagation(); cancelPreview(); }}
                                    className="text-gray-500 hover:text-white transition-colors p-1 rounded-lg hover:bg-gray-800 shrink-0 mt-0.5"
                                >
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/></svg>
                                </button>
                            </div>

                            {/* Author + Date */}
                            <div className="flex items-center justify-between gap-2">
                                <div className="flex items-center gap-2 min-w-0">
                                    {previewRoute.data.author_image
                                        ? <img src={previewRoute.data.author_image} alt="" className="w-7 h-7 rounded-full object-cover shrink-0" />
                                        : <div className="w-7 h-7 rounded-full bg-gray-700 flex items-center justify-center shrink-0">
                                            <svg className="w-4 h-4 text-gray-400" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clipRule="evenodd"/></svg>
                                          </div>
                                    }
                                    <span className="text-sm text-gray-400 truncate">{previewRoute.data.author_name || '—'}</span>
                                </div>
                                <div className="text-right text-xs text-gray-500 font-mono shrink-0">
                                    {previewRoute.data.created_at && <div>{formatDate(previewRoute.data.created_at)}</div>}
                                    {previewRoute.data.updated_at && previewRoute.data.updated_at !== previewRoute.data.created_at && (
                                        <div className="text-[11px]">ed. {formatDate(previewRoute.data.updated_at)}</div>
                                    )}
                                </div>
                            </div>

                            {/* Stats */}
                            <div className="flex items-center gap-3 text-sm font-mono">
                                <span className="text-white font-bold">{previewDistKm.toFixed(1)}<span className="text-gray-400 font-normal ml-0.5">km</span></span>
                                <span className="text-gray-600">·</span>
                                <span className="text-white font-bold">+{Math.round(previewAscentM)}<span className="text-gray-400 font-normal ml-0.5">m</span></span>
                                {previewRoute.data.stats?.views > 0 && (
                                    <>
                                        <span className="text-gray-600">·</span>
                                        <span className="text-gray-400 flex items-center gap-0.5">
                                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                                            {previewRoute.data.stats.views.toLocaleString()}
                                        </span>
                                    </>
                                )}
                            </div>

                            {/* Tags (always visible) */}
                            {previewRoute.data.tags?.length > 0 && (
                                <div className="flex flex-wrap gap-1.5">
                                    {previewRoute.data.tags.map(tag => (
                                        <span key={tag} className="bg-gray-800 text-gray-300 text-xs px-2 py-0.5 rounded-full border border-gray-700">{tag}</span>
                                    ))}
                                </div>
                            )}

                            {/* Show detail / Hide */}
                            {previewRoute.data.description && (
                                <button
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        const next = !mobilePreviewExpanded;
                                        setMobilePreviewExpanded(next);
                                        setIsElevationChartVisible(!next);
                                    }}
                                    className="text-sm text-riduck-primary font-medium flex items-center gap-1"
                                >
                                    {mobilePreviewExpanded ? 'Hide' : 'Show detail'}
                                    <svg className={`w-3 h-3 transition-transform ${mobilePreviewExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7"/></svg>
                                </button>
                            )}
                        </div>

                        {/* Scrollable: Description only */}
                        {mobilePreviewExpanded && previewRoute.data.description && (
                            <div className="flex-1 overflow-y-auto custom-scrollbar px-4 pb-2 min-h-0">
                                <div className="prose prose-sm prose-invert max-w-none text-sm">
                                    <ReactMarkdown>{previewRoute.data.description}</ReactMarkdown>
                                </div>
                            </div>
                        )}

                        {/* Action Buttons */}
                        <div className="px-4 pb-4 pt-2 grid grid-cols-2 gap-3 shrink-0 border-t border-gray-800">
                            <button
                                onClick={(e) => { e.stopPropagation(); cancelPreview(); }}
                                className="py-3 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 font-bold text-sm transition-all active:scale-[0.98]"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={(e) => { e.stopPropagation(); confirmPreviewLoad(); }}
                                className="py-3 rounded-xl bg-riduck-primary hover:bg-riduck-primary/90 text-white font-bold text-sm shadow-lg shadow-riduck-primary/20 transition-all active:scale-[0.98] flex items-center justify-center gap-1.5"
                            >
                                Load Route
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7"/></svg>
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>

        {/* Elevation Chart Panel (Collapsible) */}
        <div className="relative z-20 shrink-0">
            <div
                id="elevation-chart-panel"
                className={`relative overflow-hidden bg-gray-900/90 backdrop-blur-md transition-all duration-300 ease-in-out ${
                    isElevationChartVisible ? 'h-40 md:h-52 opacity-100' : 'h-0 opacity-0'
                }`}
            >
                <div className={`h-full px-4 transition-all duration-300 ${isElevationChartVisible ? 'pt-4 pb-0' : 'pt-0 pb-0'}`}>
                    <ElevationChart
                        segments={previewRoute
                            ? previewRoute.sections.flatMap(s => s.segments)
                            : sections.flatMap(s => s.segments)}
                        checkpoints={previewRoute
                            ? []
                            : sectionsWithPointDistances.flatMap(s => s.points)}
                        onHoverPoint={handleHoverPoint}
                        onSelectPoint={handleChartPointSelect}
                        mapHoverCoord={mapHoverCoord}
                    />
                </div>
            </div>

            <button
                type="button"
                onClick={() => setIsElevationChartVisible(prev => !prev)}
                aria-expanded={isElevationChartVisible}
                aria-controls="elevation-chart-panel"
                className="group flex w-full items-center justify-center gap-1.5 border-t border-gray-800 bg-gray-900/95 py-1.5 text-[11px] font-bold text-gray-400 transition hover:bg-gray-800/80 hover:text-white"
            >
                <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    className={`h-3.5 w-3.5 transition-transform duration-300 ${isElevationChartVisible ? '' : 'rotate-180'}`}
                >
                    <path
                        fillRule="evenodd"
                        d="M4.47 7.97a.75.75 0 011.06 0L10 12.44l4.47-4.47a.75.75 0 111.06 1.06l-5 5a.75.75 0 01-1.06 0l-5-5a.75.75 0 010-1.06z"
                        clipRule="evenodd"
                    />
                </svg>
                {isElevationChartVisible ? 'Hide Elevation' : 'Show Elevation'}
                <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    className={`h-3.5 w-3.5 transition-transform duration-300 ${isElevationChartVisible ? '' : 'rotate-180'}`}
                >
                    <path
                        fillRule="evenodd"
                        d="M4.47 7.97a.75.75 0 011.06 0L10 12.44l4.47-4.47a.75.75 0 111.06 1.06l-5 5a.75.75 0 01-1.06 0l-5-5a.75.75 0 010-1.06z"
                        clipRule="evenodd"
                    />
                </svg>
            </button>
        </div>

        {/* Save Route Modal */}
        <SaveRouteModal 
            isOpen={isSaveModalOpen}
            onClose={() => { setIsSaveModalOpen(false); pendingNearbyAfterSaveRef.current = false; }}
            onSave={handleSaveRoute}
            isLoading={isLoading}
            isOwner={user && (routeOwnerId === user.uid || routeOwnerId === user.id)}
            isMapChanged={isDirty}
            sectionsVersion={sectionsVersion}
            initialData={{
                id: currentRouteId,
                title: routeName,
                description: routeDescription,
                status: routeStatus,
                tags: routeTags
            }}
            autoTagPayload={{
                title: routeName || 'Untitled',
                editor_state: { sections: sectionsWithPointDistances }
            }}
            onAutoTagsGenerated={(newDesc, newTags, newTitle) => {
                if (newDesc) setRouteDescription(newDesc);
                if (newTags && newTags.length > 0) {
                    setRouteTags(prev => Array.from(new Set([...prev, ...newTags])));
                }
                if (newTitle && !routeName) setRouteName(newTitle);
            }}
        />
        
        <ExportRouteModal
            isOpen={isExportModalOpen}
            onClose={() => setIsExportModalOpen(false)}
            onExport={performExport}
            initialTitle={previewRoute ? (previewRoute.data.title || '') : routeName}
        />

        <NearbyFilterModal
            isOpen={isNearbyFilterOpen}
            onClose={() => setIsNearbyFilterOpen(false)}
            currentFilters={routeFilters}
            onApply={(filters) => {
                setRouteFilters(filters);
                routeFiltersRef.current = filters;
                // Re-fetch with new filters
                if (isNearbyMode) {
                    fetchNearbyRoutes();
                }
            }}
        />
      </div>

      {/* Waypoint Detail Modal */}
      {selectedWaypointId && (
        <WaypointDetailModal
          waypointId={selectedWaypointId}
          onClose={() => setSelectedWaypointId(null)}
        />
      )}
    </div>
  );
};

export default BikeRoutePlanner;
