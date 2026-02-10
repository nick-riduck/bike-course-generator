import React, { useState, useCallback, useRef, useMemo } from 'react';
import { Map, Source, Layer, Marker } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import ElevationChart from './ElevationChart';
import Sidebar from './Sidebar';

const INITIAL_VIEW_STATE = {
  longitude: 126.978,
  latitude: 37.566,
  zoom: 12
};

const generateId = () => Math.random().toString(36).substr(2, 9);

const generateGPX = (segments) => {
  if (segments.length === 0) return null;
  const header = `<?xml version="1.0" encoding="UTF-8"?><gpx version="1.1" creator="Riduck" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>`;
  const footer = `</trkseg></trk></gpx>`;
  let trkpts = '';
  segments.forEach(seg => {
    const coords = seg.geometry?.coordinates || [];
    coords.forEach(coord => {
      trkpts += `<trkpt lat="${coord[1]}" lon="${coord[0]}">${coord[2] !== undefined ? `<ele>${coord[2]}</ele>` : ''}</trkpt>`;
    });
  });
  return header + trkpts + footer;
};

const BikeRoutePlanner = () => {
  const mapRef = useRef();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  
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

  const [points, setPoints] = useState([]);
  const [segments, setSegments] = useState([]);
  const [isMockMode, setIsMockMode] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingMsg, setLoadingMsg] = useState('');
  const [hoveredCoord, setHoveredCoord] = useState(null);
  const [history, setHistory] = useState({ past: [], future: [] });
  const [hoverInfo, setHoverInfo] = useState(null);

  const handleHoverPoint = useCallback((coord) => setHoveredCoord(coord), []);

  const onHover = useCallback(event => {
    const { features, point: { x, y } } = event;
    const hoveredFeature = features && features[0];
    setHoverInfo(
      hoveredFeature && hoveredFeature.properties
        ? { feature: hoveredFeature, x, y }
        : null
    );
  }, []);

  const saveToHistory = (p, s) => setHistory(curr => ({ past: [...curr.past, { points: p, segments: s }], future: [] }));

  const handleUndo = () => {
    if (history.past.length === 0) return;
    const prev = history.past[history.past.length - 1];
    setHistory(curr => ({ past: curr.past.slice(0, -1), future: [{ points, segments }, ...curr.future] }));
    setPoints(prev.points); setSegments(prev.segments);
  };

  const handleRedo = () => {
    if (history.future.length === 0) return;
    const next = history.future[0];
    setHistory(curr => ({ past: [...curr.past, { points, segments }], future: curr.future.slice(1) }));
    setPoints(next.points); setSegments(next.segments);
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

  const handleMapClick = async (e) => {
    if (e.originalEvent.target.closest('.mapboxgl-marker')) return;
    const { lng, lat } = e.lngLat;
    const newPoint = { id: generateId(), lng, lat };
    
    saveToHistory(points, segments);
    const newPoints = [...points, newPoint];
    setPoints(newPoints);
    
    if (newPoints.length > 1) {
      const lastPoint = newPoints[newPoints.length - 2];
      const segmentId = generateId();
      const loadingSegment = { 
          id: segmentId, startPointId: lastPoint.id, endPointId: newPoint.id, 
          geometry: { type: 'LineString', coordinates: [[lastPoint.lng, lastPoint.lat], [newPoint.lng, newPoint.lat]] }, 
          distance: 0, ascent: 0, type: 'loading' 
      };
      setSegments(prev => [...prev, loadingSegment]);
      setIsLoading(true);
      try {
          const realData = await fetchSegmentData(lastPoint, newPoint, isMockMode ? 'mock' : 'real');
          if (realData) setSegments(prev => prev.map(s => s.id === segmentId ? { ...s, ...realData } : s));
          else { setSegments(prev => prev.filter(s => s.id !== segmentId)); setPoints(prev => prev.slice(0, -1)); }
      } catch(e) { }
    }
  };

  const handlePointRemove = async (index, e) => {
    e.stopPropagation();
    saveToHistory(points, segments);
    const targetPoint = points[index];
    const prevPoint = points[index - 1];
    const nextPoint = points[index + 1];
    let newSegments = segments.filter(s => s.startPointId !== targetPoint.id && s.endPointId !== targetPoint.id);
    setPoints(prev => prev.filter((_, i) => i !== index));
    if (prevPoint && nextPoint) {
      const segmentId = generateId();
      setSegments([...newSegments, { 
          id: segmentId, startPointId: prevPoint.id, endPointId: nextPoint.id, 
          geometry: { type: 'LineString', coordinates: [[prevPoint.lng, prevPoint.lat], [nextPoint.lng, nextPoint.lat]] }, 
          distance: 0, ascent: 0, type: 'loading' 
      }]);
      setIsLoading(true);
      try {
          const realData = await fetchSegmentData(prevPoint, nextPoint, isMockMode ? 'mock' : 'real');
          if (realData) setSegments(prev => prev.map(s => s.id === segmentId ? { ...s, ...realData } : s));
          else setSegments(prev => prev.filter(s => s.id !== segmentId));
      } finally { setIsLoading(false); setLoadingMsg(''); }
    } else { setSegments(newSegments); }
  };

  const totalDist = segments.reduce((acc, s) => acc + (s.distance || 0), 0);
  const totalAscent = segments.reduce((acc, s) => acc + (s.ascent || 0), 0);

  const surfaceGeoJSON = useMemo(() => ({
    type: 'FeatureCollection',
    features: segments.flatMap(s => {
        if (s.type === 'mock') return [{ type: 'Feature', geometry: s.geometry, properties: { color: '#FFA726' } }];
        if (s.type === 'loading') return [{ type: 'Feature', geometry: s.geometry, properties: { color: '#9E9E9E' } }];
        if (s.type === 'error') return [{ type: 'Feature', geometry: s.geometry, properties: { color: '#F44336' } }];
        if (s.surfaceSegments && s.surfaceSegments.length > 0) return s.surfaceSegments;
        return [{ type: 'Feature', geometry: s.geometry, properties: { color: '#2a9e92' } }];
    })
  }), [segments]);

  const handleDownloadGPX = () => {
    const gpx = generateGPX(segments); 
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

  return (
    <div className="flex w-full h-full relative">
      {/* Sidebar */}
      <Sidebar 
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
        history={history}
        onUndo={handleUndo}
        onRedo={handleRedo}
        onClear={() => { saveToHistory(points, segments); setPoints([]); setSegments([]); }}
        onSave={handleSaveRoute}
        onDownloadGPX={handleDownloadGPX}
        segments={segments}
        isMockMode={isMockMode}
        setIsMockMode={setIsMockMode}
      />

      {/* Mobile Hamburger Button */}
      <button 
        className="absolute top-4 left-4 z-20 lg:hidden p-2 bg-gray-900/90 text-white rounded-lg shadow-lg border border-gray-700"
        onClick={() => setIsSidebarOpen(true)}
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {/* Main Content (Right) */}
      <div className="flex-1 flex flex-col relative h-full">
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
                onMouseLeave={() => setHoverInfo(null)}
                interactiveLayerIds={['route-layer']}
                style={{ width: '100%', height: '100%' }} 
                cursor={isLoading ? 'wait' : 'crosshair'}
            >
                {surfaceGeoJSON.features.length > 0 && (
                    <Source id="route-source" type="geojson" data={surfaceGeoJSON}>
                        <Layer id="route-layer" type="line" layout={{ 'line-join': 'round', 'line-cap': 'round' }} paint={{ 'line-color': ['get', 'color'], 'line-width': 6, 'line-opacity': 0.9 }} />
                    </Source>
                )}
                {points.map((p, i) => (
                    <Marker key={p.id} longitude={p.lng} latitude={p.lat} anchor="center">
                    <div className={`group flex items-center justify-center w-6 h-6 rounded-full border-2 border-white shadow-lg cursor-pointer ${i === 0 ? 'bg-green-500' : i === points.length - 1 ? 'bg-red-500' : 'bg-blue-500'} text-white text-xs font-bold z-50 hover:scale-110 transition-transform`} onClick={(e) => handlePointRemove(i, e)}>
                        <span className="group-hover:hidden">{i + 1}</span><span className="hidden group-hover:block">✕</span>
                    </div>
                    </Marker>
                ))}
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
            <ElevationChart segments={segments} onHoverPoint={handleHoverPoint} />
        </div>
      </div>
    </div>
  );
};

export default BikeRoutePlanner;