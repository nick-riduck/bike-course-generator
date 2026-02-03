import React, { useState, useCallback, useRef, useMemo } from 'react';
import { Map, Source, Layer, Marker } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import ElevationChart from './ElevationChart';

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
  const [points, setPoints] = useState([]);
  const [segments, setSegments] = useState([]);
  const [isMockMode, setIsMockMode] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingMsg, setLoadingMsg] = useState('');
  const [hoveredCoord, setHoveredCoord] = useState(null);
  const [history, setHistory] = useState({ past: [], future: [] });

  const handleHoverPoint = useCallback((coord) => setHoveredCoord(coord), []);
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
            distance: 0, 
            ascent: 0, 
            type: 'mock', 
            surfaceSegments: [] 
        };
    }
    
    setLoadingMsg('Finding Route...');
    try {
      const API_BASE_URL = import.meta.env.VITE_API_URL || '';
      const response = await fetch(`${API_BASE_URL}/api/route_v2`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            locations: [{lat: start.lat, lon: start.lng}, {lat: end.lat, lon: end.lng}],
            bicycle_type: "Road",
            use_hills: 0.5,
            use_roads: 0.5
          })
      });
      
      if (!response.ok) throw new Error(`Backend error: ${response.status}`);
      const data = await response.json();
      
      const rawFeatures = data.display_geojson.features || [];
      const cleanFeatures = rawFeatures.map(f => ({
          type: 'Feature',
          geometry: {
              type: 'LineString',
              coordinates: f.geometry.coordinates
          },
          properties: {
              color: f.properties.color || '#2a9e92',
              surface: f.properties.surface || 'unknown'
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
          distance: 0, 
          ascent: 0, 
          type: 'error', 
          surfaceSegments: [] 
      };
    } finally {
        setIsLoading(false); 
        setLoadingMsg('');
    }
  };

  const handleMapClick = async (e) => {
    if (e.originalEvent.target.closest('.mapboxgl-marker') || e.originalEvent.target.closest('button')) return;
    const { lng, lat } = e.lngLat;
    const newPoint = { id: generateId(), lng, lat };
    
    saveToHistory(points, segments);
    
    const newPoints = [...points, newPoint];
    setPoints(newPoints);
    
    if (newPoints.length > 1) {
      const lastPoint = newPoints[newPoints.length - 2];
      const segmentId = generateId();
      
      const loadingSegment = { 
          id: segmentId, 
          startPointId: lastPoint.id, 
          endPointId: newPoint.id, 
          geometry: { type: 'LineString', coordinates: [[lastPoint.lng, lastPoint.lat], [newPoint.lng, newPoint.lat]] }, 
          distance: 0, 
          ascent: 0, 
          type: 'loading' 
      };
      
      setSegments(prev => [...prev, loadingSegment]);
      setIsLoading(true);
      
      try {
          const realData = await fetchSegmentData(lastPoint, newPoint, isMockMode ? 'mock' : 'real');
          setSegments(prev => prev.map(s => s.id === segmentId ? { ...s, ...realData } : s));
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
          id: segmentId, 
          startPointId: prevPoint.id, 
          endPointId: nextPoint.id, 
          geometry: { type: 'LineString', coordinates: [[prevPoint.lng, prevPoint.lat], [nextPoint.lng, nextPoint.lat]] }, 
          distance: 0, 
          ascent: 0, 
          type: 'loading' 
      }]);
      
      setIsLoading(true);
      try {
          const realData = await fetchSegmentData(prevPoint, nextPoint, isMockMode ? 'mock' : 'real');
          setSegments(prev => prev.map(s => s.id === segmentId ? { ...s, ...realData } : s));
      } finally { setIsLoading(false); setLoadingMsg(''); }
    } else { 
        setSegments(newSegments); 
    }
  };

  const totalDist = segments.reduce((acc, s) => acc + (s.distance || 0), 0);
  const totalAscent = segments.reduce((acc, s) => acc + (s.ascent || 0), 0);

  const surfaceGeoJSON = useMemo(() => ({
    type: 'FeatureCollection',
    features: segments.flatMap(s => {
        if (s.type === 'mock') return [{ type: 'Feature', geometry: s.geometry, properties: { color: '#FFA726', type: 'mock' } }];
        if (s.type === 'loading') return [{ type: 'Feature', geometry: s.geometry, properties: { color: '#9E9E9E', type: 'loading' } }];
        if (s.type === 'error') return [{ type: 'Feature', geometry: s.geometry, properties: { color: '#F44336', type: 'error' } }];
        
        if (s.surfaceSegments && s.surfaceSegments.length > 0) {
            return s.surfaceSegments;
        }
        
        return [{ type: 'Feature', geometry: s.geometry, properties: { color: '#2a9e92', type: 'api' } }];
    })
  }), [segments]);

  return (
    <div className="flex flex-col gap-4 relative">
      {isLoading && <div className="absolute inset-0 z-[9999] bg-black/60 backdrop-blur-sm flex flex-col items-center justify-center rounded-xl"><div className="animate-spin rounded-full h-10 w-10 border-b-2 border-riduck-primary mb-3"></div><div className="text-white text-sm font-bold animate-pulse">{loadingMsg}</div></div>}
      
      <div className="relative w-full h-[600px] rounded-xl overflow-hidden border border-gray-700 shadow-2xl">
        <Map 
            ref={mapRef} 
            initialViewState={INITIAL_VIEW_STATE} 
            mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json" 
            onClick={handleMapClick} 
            style={{ width: '100%', height: '100%' }} 
            cursor={isLoading ? 'wait' : 'crosshair'}
        >
          {surfaceGeoJSON.features.length > 0 && (
            <Source 
                id="route-source" 
                key={`route-src-${Date.now()}`} 
                type="geojson" 
                data={surfaceGeoJSON}
            >
                <Layer 
                    id="route-layer" 
                    type="line" 
                    layout={{ 'line-join': 'round', 'line-cap': 'round' }} 
                    paint={{ 
                        'line-color': ['get', 'color'], 
                        'line-width': 8, 
                        'line-opacity': 0.9
                    }} 
                />
            </Source>
          )}
          
          {points.map((p, i) => (
            <Marker key={p.id} longitude={p.lng} latitude={p.lat} anchor="center">
              <div className={`group flex items-center justify-center w-5 h-5 rounded-full border-2 border-white shadow-lg cursor-pointer ${i === 0 ? 'bg-green-500' : i === points.length - 1 ? 'bg-red-500' : 'bg-blue-500'} text-white text-[10px] font-bold z-50`} onClick={(e) => handlePointRemove(i, e)}>
                <span className="group-hover:hidden">{i + 1}</span><span className="hidden group-hover:block">X</span>
              </div>
            </Marker>
          ))}
          
          {hoveredCoord && <Marker key={`hover-${hoveredCoord.lng}-${hoveredCoord.lat}`} longitude={hoveredCoord.lng} latitude={hoveredCoord.lat} anchor="center" style={{ zIndex: 99999 }}><div className="w-2.5 h-2.5 rounded-full bg-yellow-400 border border-white pointer-events-none"></div></Marker>}
        </Map>
        
        {/* NEW LEGEND POSITION */}
        <div className="absolute bottom-6 left-4 z-50">
          <div className="p-4 bg-gray-900/95 backdrop-blur rounded-xl border border-gray-700 shadow-2xl text-white min-w-[200px]">
            <div className="flex justify-between items-center mb-3">
                <span className="font-bold text-base text-white">Route Legend</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs text-gray-300">
                <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-[#2a9e92]"></div>Road</div>
                <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-[#00E676]"></div>Cycleway</div>
                <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-[#FF9800]"></div>Gravel/Dirt</div>
                <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-[#FFC107]"></div>Path</div>
                <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-[#4FC3F7]"></div>Residential</div>
                <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-[#00695C]"></div>Main Road</div>
            </div>
          </div>
        </div>

        <div className="absolute top-4 left-4 z-50 flex flex-col gap-2">
          <div className="p-3 bg-gray-900/90 backdrop-blur rounded-lg border border-gray-700 shadow text-white min-w-[160px]">
            <div className="flex justify-between items-center mb-2"><span className="font-bold text-teal-400">Route Stats</span></div>
            <div className="grid grid-cols-2 gap-2 mb-3">
              <div><p className="text-[9px] uppercase text-gray-500">Dist</p><p className="text-sm font-mono">{totalDist.toFixed(1)}km</p></div>
              <div><p className="text-[9px] uppercase text-gray-500">Ascent</p><p className="text-sm font-mono">{Math.round(totalAscent)}m</p></div>
            </div>
            
            <div className="flex items-center justify-between bg-gray-800 p-1.5 rounded mb-2"><span className="text-[10px] text-gray-400">Mock</span><button onClick={() => setIsMockMode(!isMockMode)} className={`w-7 h-3.5 rounded-full relative ${isMockMode ? 'bg-yellow-500' : 'bg-gray-600'}`}><div className={`absolute top-0.5 w-2.5 h-2.5 bg-white rounded-full transition-all ${isMockMode ? 'left-4' : 'left-0.5'}`} /></button></div>
            <div className="flex gap-1 mb-2"><button onClick={handleUndo} disabled={history.past.length === 0} className="flex-1 bg-gray-700 py-1 rounded text-[10px] disabled:opacity-30">Undo</button><button onClick={handleRedo} disabled={history.future.length === 0} className="flex-1 bg-gray-700 py-1 rounded text-[10px] disabled:opacity-30">Redo</button><button onClick={() => { saveToHistory(points, segments); setPoints([]); setSegments([]); }} className="flex-1 bg-red-900/40 py-1 rounded text-[10px]">Clear</button></div>
            <button onClick={() => { const gpx = generateGPX(segments); if(gpx) { const blob = new Blob([gpx], { type: 'application/gpx+xml' }); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `route-${Date.now()}.gpx`; a.click(); } }} disabled={segments.length === 0} className="w-full bg-teal-700 py-1.5 rounded text-[10px] font-bold">GPX Download</button>
          </div>
        </div>
      </div>
      <ElevationChart segments={segments} onHoverPoint={handleHoverPoint} />
    </div>
  );
};

export default BikeRoutePlanner;