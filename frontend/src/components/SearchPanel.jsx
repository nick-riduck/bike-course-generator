import React, { useState, useEffect } from 'react';
import { useAuth } from '../AuthContext';
import { auth } from '../firebase';

const formatRelativeTime = (dateString) => {
    if (!dateString) return '';
    const now = new Date();
    const date = new Date(dateString);
    const diff = now - date;
    const diffDays = Math.floor(diff / (1000 * 60 * 60 * 24));
    
    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays}d ago`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
};

const SearchPanel = ({ onLoadRoute }) => {
  const { user } = useAuth();
  const [searchQuery, setSearchQuery] = useState('');
  const [myRoutes, setMyRoutes] = useState([]);
  const [publicRoutes, setPublicRoutes] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchAll();
  }, [user, searchQuery]);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const headers = {};
      if (auth.currentUser) {
        const idToken = await auth.currentUser.getIdToken();
        headers['Authorization'] = `Bearer ${idToken}`;
      }

      // 1. Fetch My Routes (only if logged in)
      if (user) {
        const myRes = await fetch(`/api/routes?scope=my${searchQuery ? `&q=${searchQuery}` : ''}`, { headers });
        if (myRes.ok) {
          const data = await myRes.json();
          setMyRoutes(data.routes || []);
        }
      } else {
        setMyRoutes([]);
      }

      // 2. Fetch Public Routes
      const pubRes = await fetch(`/api/routes?scope=public${searchQuery ? `&q=${searchQuery}` : ''}`, { headers });
      if (pubRes.ok) {
        const data = await pubRes.json();
        setPublicRoutes(data.routes || []);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const renderRouteCard = (route, isMyRoute) => (
      <div 
          key={route.id}
          onClick={() => onLoadRoute(route.id)}
          className="p-0 bg-gray-800/40 hover:bg-gray-800 border border-gray-700/50 hover:border-riduck-primary rounded-xl cursor-pointer transition-all group overflow-hidden flex flex-col"
      >
          {/* Thumbnail Area */}
          <div className="h-20 bg-[#111827] relative overflow-hidden border-b border-gray-800 shrink-0">
              {route.thumbnail_url ? (
                  <img 
                      src={route.thumbnail_url} 
                      alt={route.title}
                      className="w-full h-full object-contain group-hover:scale-105 transition-transform duration-500 opacity-90 group-hover:opacity-100"
                  />
              ) : (
                  <div className="w-full h-full flex items-center justify-center text-gray-700">
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
                      </svg>
                  </div>
              )}
              
              {/* Badges */}
              <div className="absolute top-2 left-2 flex gap-1">
                  {isMyRoute && (
                      <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold border ${
                          route.status === 'PUBLIC' ? 'bg-green-500/20 text-green-400 border-green-500/30' : 
                          route.status === 'PRIVATE' ? 'bg-red-500/20 text-red-400 border-red-500/30' : 
                          'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
                      }`}>
                          {route.status === 'LINK_ONLY' ? 'LINK' : route.status}
                      </span>
                  )}
                  {!isMyRoute && route.author_name && (
                      <span className="bg-gray-900/80 text-gray-300 px-1.5 py-0.5 text-[8px] rounded border border-gray-700 backdrop-blur-sm">
                          by {route.author_name}
                      </span>
                  )}
              </div>

              <div className="absolute top-2 right-2">
                  <span className="text-[9px] text-gray-400 bg-black/60 backdrop-blur-sm px-1.5 py-0.5 rounded font-mono border border-white/10">#{route.route_num}</span>
              </div>
          </div>

          {/* Info Area */}
          <div className="p-3 flex flex-col gap-2">
              {/* Row 1: Title & Date */}
              <div className="flex justify-between items-start">
                  <h4 className="text-sm font-bold text-gray-200 group-hover:text-white truncate flex-1 pr-2" title={route.title}>
                      {route.title}
                  </h4>
                  <span 
                      className="text-[9px] text-gray-500 whitespace-nowrap shrink-0 mt-0.5 cursor-help border-b border-dotted border-gray-600/50"
                      title={`Created: ${new Date(route.created_at).toLocaleString()}\nUpdated: ${new Date(route.updated_at || route.created_at).toLocaleString()}`}
                  >
                      {formatRelativeTime(route.updated_at || route.created_at)}
                  </span>
              </div>

              {/* Row 2: Stats */}
              <div className="flex items-center gap-3 text-xs text-gray-400">
                  <div className="flex items-center gap-1" title="Distance">
                      <span className="text-[10px]">📏</span>
                      <span className="font-mono text-white font-bold">{(route.distance / 1000).toFixed(1)}km</span>
                  </div>
                  <div className="flex items-center gap-1" title="Elevation Gain">
                      <span className="text-[10px]">⛰️</span>
                      <span className="font-mono text-white font-bold">{Math.round(route.elevation_gain)}m</span>
                  </div>
              </div>
              
              {/* Row 3: Tags & Load Action */}
              <div className="flex justify-between items-end h-5">
                  <div 
                      className="flex flex-wrap gap-1 overflow-hidden h-full items-center"
                      title={route.tags ? route.tags.join(', ') : ''}
                  >
                      {route.tags && route.tags.slice(0, 3).map(tag => (
                          <span key={tag} className="text-[9px] text-riduck-primary bg-riduck-primary/10 px-1.5 py-0.5 rounded-md">#{tag}</span>
                      ))}
                      {route.tags && route.tags.length > 3 && (
                          <span className="text-[9px] text-gray-600">+{route.tags.length - 3}</span>
                      )}
                  </div>
                  
                  <span className="text-[9px] font-bold text-riduck-primary opacity-0 group-hover:opacity-100 transition-opacity transform translate-x-2 group-hover:translate-x-0 shrink-0">
                      LOAD &rarr;
                  </span>
              </div>
          </div>
      </div>
  );


  return (
    <div className="w-80 h-full bg-gray-900 border-r border-gray-800 flex flex-col animate-fadeIn shadow-xl z-40">
      {/* 1. Header & Search */}
      <div className="p-4 border-b border-gray-800">
        <h2 className="font-bold text-white text-lg mb-4">Library</h2>
        
        <div className="relative">
          <input 
            type="text" 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Not supported yet (미지원)" 
            disabled
            className="w-full bg-gray-800 text-gray-500 px-4 py-2.5 rounded-xl border border-gray-700 focus:outline-none text-xs cursor-not-allowed opacity-60"
          />
          <span className="absolute right-3 top-2.5 text-gray-600 text-xs">🔍</span>
        </div>
        
        {/* Search Scope Filter (Disabled) */}
        <div className="flex gap-2 text-[10px] mt-3 opacity-50 cursor-not-allowed">
            <span className="px-2 py-1 bg-gray-800 text-gray-500 rounded border border-gray-700">All</span>
            <span className="px-2 py-1 bg-gray-800 text-gray-500 rounded border border-gray-700">My Routes</span>
            <span className="px-2 py-1 bg-gray-800 text-gray-500 rounded border border-gray-700">Open Courses</span>
        </div>
      </div>

      {/* 2. Scrollable Content */}
      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
          {/* Section: My Routes */}
          <div className="mb-6">
              <h3 className="text-[10px] font-bold text-gray-500 uppercase mb-2 px-1">My Routes</h3>
              
              {!user ? (
                 <div className="flex flex-col items-center justify-center text-center p-6 border-2 border-dashed border-gray-800 rounded-xl bg-gray-900/30">
                    <p className="text-xs text-gray-500 mb-2">Login to save your routes.</p>
                 </div>
              ) : loading && myRoutes.length === 0 ? (
                 <div className="flex justify-center p-4"><div className="animate-spin h-5 w-5 border-2 border-riduck-primary rounded-full border-t-transparent"></div></div>
              ) : myRoutes.length === 0 ? (
                 <div className="flex flex-col items-center justify-center text-center p-6 border-2 border-dashed border-gray-800 rounded-xl bg-gray-900/30">
                    <div className="w-8 h-8 bg-gray-800 rounded-full flex items-center justify-center mb-2 text-gray-600">👤</div>
                    <p className="text-xs text-gray-600">No personal routes found.</p>
                 </div>
              ) : (
                 <div className="space-y-3">
                    {myRoutes.map(route => renderRouteCard(route, true))}
                 </div>
              )}
          </div>

          {/* Section: Open Routes */}
          <div>
              <h3 className="text-[10px] font-bold text-gray-500 uppercase mb-2 px-1">Open Routes</h3>
              
              {loading && publicRoutes.length === 0 ? (
                 <div className="flex justify-center p-4"><div className="animate-spin h-5 w-5 border-2 border-riduck-primary rounded-full border-t-transparent"></div></div>
              ) : publicRoutes.length === 0 ? (
                 <div className="flex flex-col items-center justify-center text-center p-6 border-2 border-dashed border-gray-800 rounded-xl bg-gray-900/30">
                    <div className="w-8 h-8 bg-gray-800 rounded-full flex items-center justify-center mb-2 text-gray-600">🌍</div>
                    <p className="text-xs text-gray-600">No public courses found.</p>
                 </div>
              ) : (
                 <div className="space-y-3">
                    {publicRoutes.map(route => renderRouteCard(route, false))}
                 </div>
              )}
          </div>
      </div>
    </div>
  );
};

export default SearchPanel;