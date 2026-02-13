import React, { useState, useEffect, useRef, useCallback } from 'react';
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
  const [activeTab, setActiveTab] = useState('all'); // 'all', 'my', 'public'
  const [sortOption, setSortOption] = useState('latest'); // latest, updated, popular, distance, elevation
  
  // Data States
  const [myRoutes, setMyRoutes] = useState([]);
  const [publicRoutes, setPublicRoutes] = useState([]);
  
  // Pagination States
  const [page, setPage] = useState(1);
  const [hasMoreMy, setHasMoreMy] = useState(true);
  const [hasMorePublic, setHasMorePublic] = useState(true);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  // Scroll Ref
  const scrollContainerRef = useRef(null);

  // 1. Initial Load & Tab Change & Search Change & Sort Change
  useEffect(() => {
    setPage(1);
    setMyRoutes([]);
    setPublicRoutes([]);
    setHasMoreMy(true);
    setHasMorePublic(true);
    fetchData(1, true);
  }, [user, searchQuery, activeTab, sortOption]);

  // 2. Fetch Data Logic
  const fetchData = async (pageNum, isReset = false) => {
    const isLoadMore = pageNum > 1;
    if (isLoadMore) setLoadingMore(true);
    else setLoading(true);

    try {
      const headers = {};
      if (auth.currentUser) {
        const idToken = await auth.currentUser.getIdToken();
        headers['Authorization'] = `Bearer ${idToken}`;
      }

      const limit = 10;
      
      // Determine what to fetch based on activeTab
      const fetchMy = (activeTab === 'all' || activeTab === 'my') && user;
      const fetchPublic = (activeTab === 'all' || activeTab === 'public');

      // Helper to fetch a specific scope
      const fetchScope = async (scope) => {
        const res = await fetch(`/api/routes?scope=${scope}${searchQuery ? `&q=${searchQuery}` : ''}&page=${pageNum}&limit=${limit}&sort=${sortOption}`, { headers });
        if (res.ok) {
          const data = await res.json();
          return data.routes || [];
        }
        return [];
      };

      if (fetchMy) {
        // If tab is 'all', we only fetch the first page once (Overview)
        // If tab is 'my', we fetch normally with pagination
        if (activeTab === 'my' || (activeTab === 'all' && pageNum === 1)) {
            const newMyRoutes = await fetchScope('my');
            if (activeTab === 'my') {
                setMyRoutes(prev => isReset ? newMyRoutes : [...prev, ...newMyRoutes]);
                setHasMoreMy(newMyRoutes.length === limit);
            } else {
                // Overview mode: just take top 3
                setMyRoutes(newMyRoutes.slice(0, 3));
            }
        }
      }

      if (fetchPublic) {
        if (activeTab === 'public' || (activeTab === 'all' && pageNum === 1)) {
            const newPublicRoutes = await fetchScope('public');
            if (activeTab === 'public') {
                setPublicRoutes(prev => isReset ? newPublicRoutes : [...prev, ...newPublicRoutes]);
                setHasMorePublic(newPublicRoutes.length === limit);
            } else {
                // Overview mode: just take top 3
                setPublicRoutes(newPublicRoutes.slice(0, 3));
            }
        }
      }

    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  };

  // 3. Infinite Scroll Handler
  const handleScroll = useCallback(() => {
    if (activeTab === 'all') return; // No infinite scroll in overview
    if (loading || loadingMore) return;

    const container = scrollContainerRef.current;
    if (!container) return;

    // Check if scrolled near bottom
    if (container.scrollHeight - container.scrollTop <= container.clientHeight + 50) {
        if ((activeTab === 'my' && hasMoreMy) || (activeTab === 'public' && hasMorePublic)) {
            const nextPage = page + 1;
            setPage(nextPage);
            fetchData(nextPage, false);
        }
    }
  }, [activeTab, loading, loadingMore, hasMoreMy, hasMorePublic, page]);

  // Attach Scroll Listener
  useEffect(() => {
      const container = scrollContainerRef.current;
      if (container) {
          container.addEventListener('scroll', handleScroll);
          return () => container.removeEventListener('scroll', handleScroll);
      }
  }, [handleScroll]);


  // 4. Delete Handler
  const handleDeleteRoute = async (e, routeId) => {
      e.stopPropagation(); // Prevent card click
      if (!window.confirm("Are you sure you want to delete this route?")) return;

      try {
          const idToken = await auth.currentUser.getIdToken();
          const res = await fetch(`/api/routes/${routeId}`, {
              method: 'DELETE',
              headers: { 'Authorization': `Bearer ${idToken}` }
          });

          if (res.ok) {
              // Remove from local state immediately
              setMyRoutes(prev => prev.filter(r => r.id !== routeId));
          } else {
              alert("Failed to delete route.");
          }
      } catch (err) {
          console.error(err);
          alert("Error deleting route.");
      }
  };

  const renderRouteCard = (route, isMyRoute) => (
      <div 
          key={route.id}
          onClick={() => onLoadRoute(route.id)}
          className="p-0 bg-gray-800/40 hover:bg-gray-800 border border-gray-700/50 hover:border-riduck-primary rounded-xl cursor-pointer transition-all group overflow-hidden flex flex-col relative"
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
                      <span className={`px-1.5 py-0.5 text-[8px] rounded border backdrop-blur-sm ${
                          user && route.user_id === user.uid
                          ? 'bg-riduck-primary/20 text-riduck-primary border-riduck-primary/30 font-bold'
                          : 'bg-gray-900/80 text-gray-300 border-gray-700'
                      }`}>
                          by {user && route.user_id === user.uid ? 'ME' : route.author_name}
                      </span>
                  )}
              </div>

              {/* Route Number or Delete Button */}
              <div className="absolute top-2 right-2 flex gap-1">
                  <span className="text-[9px] text-gray-400 bg-black/60 backdrop-blur-sm px-1.5 py-0.5 rounded font-mono border border-white/10 h-5 flex items-center">#{route.route_num}</span>
                  {isMyRoute && (
                      <button 
                          onClick={(e) => handleDeleteRoute(e, route.id)}
                          className="bg-red-500/80 hover:bg-red-600 text-white w-5 h-5 rounded flex items-center justify-center backdrop-blur-sm transition-colors z-10"
                          title="Delete Route"
                      >
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                              <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                          </svg>
                      </button>
                  )}
              </div>
          </div>

          {/* Info Area */}
          <div className="p-3 flex flex-col gap-2">
              {/* Row 1: Title & Date */}
              <div className="flex justify-between items-start">
                  <h4 className="text-sm font-bold text-gray-200 group-hover:text-white truncate flex-1 pr-2" title={route.title}>
                      {route.title}
                  </h4>
                  <div className="flex flex-col items-end">
                      <span 
                          className="text-[9px] text-gray-500 whitespace-nowrap shrink-0 cursor-help border-b border-dotted border-gray-600/50"
                          title={`Created: ${new Date(route.created_at).toLocaleString()}\nUpdated: ${new Date(route.updated_at || route.created_at).toLocaleString()}`}
                      >
                          {formatRelativeTime(route.updated_at || route.created_at)}
                      </span>
                      {/* Stats: Views & Downloads */}
                      <div className="flex items-center gap-2 mt-1 text-[9px] text-gray-600">
                          <span title="Views">👁️ {route.view_count || 0}</span>
                          <span title="Downloads">⬇️ {route.download_count || 0}</span>
                      </div>
                  </div>
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
                      {route.tags && route.tags.length > 0 ? (
                          <>
                              {route.tags.slice(0, 3).map(tag => (
                                  <span key={tag} className="text-[9px] text-riduck-primary bg-riduck-primary/10 px-1.5 py-0.5 rounded-md">#{tag}</span>
                              ))}
                              {route.tags.length > 3 && (
                                  <span className="text-[9px] text-gray-600">+{route.tags.length - 3}</span>
                              )}
                          </>
                      ) : (
                          <span className="text-[9px] text-gray-500 bg-gray-800/50 px-1.5 py-0.5 rounded-md italic">no tags</span>
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
        <div className="flex justify-between items-center mb-4">
            <h2 className="font-bold text-white text-lg">Library</h2>
            {/* Sort Dropdown */}
            <select 
                value={sortOption} 
                onChange={(e) => setSortOption(e.target.value)}
                className="bg-gray-800 text-gray-400 text-[10px] px-2 py-1 rounded border border-gray-700 focus:outline-none"
            >
                <option value="latest">Latest</option>
                <option value="updated">Updated</option>
                <option value="popular">Popular</option>
                <option value="distance">Distance</option>
                <option value="elevation">Elevation</option>
            </select>
        </div>
        
        <div className="relative">
          <input 
            type="text" 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search routes..." 
            className="w-full bg-gray-800 text-gray-200 px-4 py-2.5 rounded-xl border border-gray-700 focus:outline-none focus:border-riduck-primary text-xs"
          />
          <span className="absolute right-3 top-2.5 text-gray-600 text-xs">🔍</span>
        </div>
        
        {/* Search Scope Filter */}
        <div className="flex gap-2 text-[10px] mt-3">
            <button 
                onClick={() => setActiveTab('all')}
                className={`px-3 py-1.5 rounded-lg border transition-all ${
                    activeTab === 'all' 
                    ? 'bg-riduck-primary/20 text-riduck-primary border-riduck-primary/50 font-bold' 
                    : 'bg-gray-800 text-gray-500 border-gray-700 hover:bg-gray-700'
                }`}
            >
                Overview
            </button>
            <button 
                onClick={() => setActiveTab('my')}
                className={`px-3 py-1.5 rounded-lg border transition-all ${
                    activeTab === 'my' 
                    ? 'bg-riduck-primary/20 text-riduck-primary border-riduck-primary/50 font-bold' 
                    : 'bg-gray-800 text-gray-500 border-gray-700 hover:bg-gray-700'
                }`}
            >
                My Routes
            </button>
            <button 
                onClick={() => setActiveTab('public')}
                className={`px-3 py-1.5 rounded-lg border transition-all ${
                    activeTab === 'public' 
                    ? 'bg-riduck-primary/20 text-riduck-primary border-riduck-primary/50 font-bold' 
                    : 'bg-gray-800 text-gray-500 border-gray-700 hover:bg-gray-700'
                }`}
            >
                Open Routes
            </button>
        </div>
      </div>

      {/* 2. Scrollable Content */}
      <div 
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto p-4 custom-scrollbar"
      >
          
          {/* Section: My Routes */}
          {(activeTab === 'all' || activeTab === 'my') && (
            <div className="mb-6">
                <div className="flex justify-between items-center mb-2 px-1">
                    <h3 className="text-[10px] font-bold text-gray-500 uppercase">My Routes</h3>
                    {activeTab === 'all' && myRoutes.length > 0 && (
                        <button 
                            onClick={() => setActiveTab('my')}
                            className="text-[10px] text-riduck-primary hover:underline"
                        >
                            See All &rarr;
                        </button>
                    )}
                </div>
                
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
          )}

          {/* Section: Open Routes */}
          {(activeTab === 'all' || activeTab === 'public') && (
            <div>
                <div className="flex justify-between items-center mb-2 px-1">
                    <h3 className="text-[10px] font-bold text-gray-500 uppercase">Open Routes</h3>
                    {activeTab === 'all' && publicRoutes.length > 0 && (
                        <button 
                            onClick={() => setActiveTab('public')}
                            className="text-[10px] text-riduck-primary hover:underline"
                        >
                            See All &rarr;
                        </button>
                    )}
                </div>
                
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
          )}

          {/* Infinite Scroll Loader */}
          {loadingMore && (
              <div className="py-4 flex justify-center">
                  <div className="animate-spin h-5 w-5 border-2 border-riduck-primary rounded-full border-t-transparent"></div>
              </div>
          )}
          {!loading && !loadingMore && activeTab !== 'all' && (
              ((activeTab === 'my' && !hasMoreMy && myRoutes.length > 0) || (activeTab === 'public' && !hasMorePublic && publicRoutes.length > 0)) && (
                  <div className="py-6 text-center">
                      <p className="text-[10px] text-gray-600 uppercase tracking-widest">No more routes</p>
                  </div>
              )
          )}
      </div>
    </div>
  );
};

export default SearchPanel;