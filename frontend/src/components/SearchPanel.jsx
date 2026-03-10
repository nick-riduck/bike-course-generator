import React, { useState, useEffect, useRef, useCallback } from 'react';
import apiClient from '../utils/apiClient';
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

const SearchPanel = ({ onLoadRoute, activePreviewId, routeFilters, onFiltersChange, refreshTrigger }) => {
  const { user } = useAuth();
  const [searchQuery, setSearchQuery] = useState('');
  const [activeTab, setActiveTab] = useState('all'); // 'all', 'my', 'favorites'
  const [sortOption, setSortOption] = useState('latest'); // latest, updated, popular, distance, elevation
  const [sortOrder, setSortOrder] = useState('desc'); // 'asc' or 'desc'

  // Data States
  const [myRoutes, setMyRoutes] = useState([]);
  const [publicRoutes, setPublicRoutes] = useState([]);

  // UI States
  const [page, setPage] = useState(1);
  const [hasMoreMy, setHasMoreMy] = useState(true);
  const [hasMorePublic, setHasMorePublic] = useState(true);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);

  // Filter UI States
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [allTags, setAllTags] = useState([]);
  const [tagQuery, setTagQuery] = useState('');
  const [showTagDropdown, setShowTagDropdown] = useState(false);
  const [tagSuggestions, setTagSuggestions] = useState([]);
  const [searchTagSuggestions, setSearchTagSuggestions] = useState([]);
  const tagDebounceRef = useRef(null);
  const searchTagDebounceRef = useRef(null);
  const tagInputRef = useRef(null);
  const tagDropdownRef = useRef(null);
  const searchInputRef = useRef(null);
  const searchTagDropdownRef = useRef(null);
  const [showSearchTagDropdown, setShowSearchTagDropdown] = useState(false);

  // Scroll Ref
  const scrollContainerRef = useRef(null);

  const hasActiveFilters = routeFilters &&
      (routeFilters.minDistance !== '' || routeFilters.maxDistance !== '' ||
       routeFilters.minElevation !== '' || routeFilters.maxElevation !== '' ||
       routeFilters.tags.length > 0);

  // Fetch tags on mount (needed for search autocomplete + filter panel)
  useEffect(() => {
      if (allTags.length === 0) {
          fetch('/api/routes/tags')
              .then(res => res.ok ? res.json() : [])
              .then(setAllTags)
              .catch(() => setAllTags([]));
      }
  }, [allTags.length]);

  // Close tag dropdowns on outside click
  useEffect(() => {
      const handleClick = (e) => {
          if (tagDropdownRef.current && !tagDropdownRef.current.contains(e.target) &&
              tagInputRef.current && !tagInputRef.current.contains(e.target)) {
              setShowTagDropdown(false);
          }
          if (searchTagDropdownRef.current && !searchTagDropdownRef.current.contains(e.target) &&
              searchInputRef.current && !searchInputRef.current.contains(e.target)) {
              setShowSearchTagDropdown(false);
          }
      };
      document.addEventListener('mousedown', handleClick);
      return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  // Semantic tag search for filter panel
  const fetchTagSuggestions = useCallback(async (query, setter) => {
      try {
          const url = query.trim()
              ? `/api/routes/tags/search?q=${encodeURIComponent(query.trim())}`
              : '/api/routes/tags/search';
          const res = await fetch(url);
          if (res.ok) setter(await res.json());
      } catch (err) {
          console.error('Tag search error:', err);
      }
  }, []);

  const filteredTags = tagSuggestions.filter(t =>
      routeFilters && !routeFilters.tags.includes(t.slug)
  );

  const searchFilteredTags = searchTagSuggestions.filter(t =>
      routeFilters && !routeFilters.tags.includes(t.slug)
  );

  // 2. Fetch Data Logic
  const fetchData = useCallback(async (pageNum, isReset = false) => {
    const isLoadMore = pageNum > 1;
    if (isLoadMore) setLoadingMore(true);
    else {
        setLoading(true);
        setError(null);
    }

    try {
      const limit = 10;
      
      // Favorites tab has no data yet
      if (activeTab === 'favorites') {
        setLoading(false);
        return;
      }

      // Helper to fetch a specific scope
      const fetchScope = async (scope) => {
        const params = new URLSearchParams({
            scope, page: pageNum, limit, sort: sortOption, order: sortOrder
        });
        if (searchQuery) params.set('q', searchQuery);
        if (routeFilters) {
            if (routeFilters.minDistance !== '') params.set('min_distance', routeFilters.minDistance);
            if (routeFilters.maxDistance !== '') params.set('max_distance', routeFilters.maxDistance);
            if (routeFilters.minElevation !== '') params.set('min_elevation', routeFilters.minElevation);
            if (routeFilters.maxElevation !== '') params.set('max_elevation', routeFilters.maxElevation);
            if (routeFilters.tags.length > 0) params.set('tags', routeFilters.tags.join(','));
        }
        const data = await apiClient.get(`/api/routes?${params}`);
        return data.routes || [];
      };

      if (activeTab === 'my' && user) {
        const newMyRoutes = await fetchScope('my');
        setMyRoutes(prev => isReset ? newMyRoutes : [...prev, ...newMyRoutes]);
        setHasMoreMy(newMyRoutes.length === limit);
      }

      if (activeTab === 'all') {
        const newPublicRoutes = await fetchScope('public');
        setPublicRoutes(prev => isReset ? newPublicRoutes : [...prev, ...newPublicRoutes]);
        setHasMorePublic(newPublicRoutes.length === limit);
      }

    } catch (e) {
      console.error(e);
      setError("Network error. Please check your connection.");
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [user, searchQuery, activeTab, sortOption, sortOrder, routeFilters]);

  // 1. Initial Load & Tab Change & Search Change & Sort Change & Filter Change
  useEffect(() => {
    setPage(1);
    setMyRoutes([]);
    setPublicRoutes([]);
    setHasMoreMy(true);
    setHasMorePublic(true);
    fetchData(1, true);
  }, [user, searchQuery, activeTab, sortOption, sortOrder, routeFilters, fetchData, refreshTrigger]);

  // 3. Infinite Scroll Handler
  const handleScroll = useCallback(() => {
    if (activeTab === 'favorites') return; // No infinite scroll in favorites
    if (loading || loadingMore || error) return;

    const container = scrollContainerRef.current;
    if (!container) return;

    // Check if scrolled near bottom
    if (container.scrollHeight - container.scrollTop <= container.clientHeight + 50) {
        if ((activeTab === 'my' && hasMoreMy) || (activeTab === 'all' && hasMorePublic)) {
            const nextPage = page + 1;
            setPage(nextPage);
            fetchData(nextPage, false);
        }
    }
  }, [activeTab, loading, loadingMore, error, hasMoreMy, hasMorePublic, page, fetchData]);

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
          onClick={() => onLoadRoute(route.id)}
          className={`p-0 bg-gray-800/40 hover:bg-gray-800 border rounded-xl cursor-pointer transition-all group overflow-hidden flex flex-col relative ${
              activePreviewId === route.id
                  ? 'border-riduck-primary bg-gray-800 ring-1 ring-riduck-primary/30'
                  : 'border-gray-700/50 hover:border-riduck-primary'
          }`}
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
            <div className="flex items-center gap-2">
                {/* Filter Toggle */}
                <button
                    onClick={() => setIsFilterOpen(prev => !prev)}
                    className={`relative px-2 py-1 rounded border transition-all ${
                        isFilterOpen || hasActiveFilters
                        ? 'bg-riduck-primary/20 text-riduck-primary border-riduck-primary/50'
                        : 'bg-gray-800 text-gray-500 border-gray-700 hover:bg-gray-700'
                    }`}
                    title="필터"
                >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
                    </svg>
                    {hasActiveFilters && (
                        <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-riduck-primary rounded-full border-2 border-gray-900" />
                    )}
                </button>
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
                {/* Sort Order Toggle */}
                <button
                    onClick={() => setSortOrder(prev => prev === 'desc' ? 'asc' : 'desc')}
                    className="bg-gray-800 text-gray-400 hover:text-gray-200 px-1.5 py-1 rounded border border-gray-700 hover:bg-gray-700 transition-all"
                    title={sortOrder === 'desc' ? '내림차순' : '오름차순'}
                >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        {sortOrder === 'desc' ? (
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        ) : (
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                        )}
                    </svg>
                </button>
            </div>
        </div>

        <div className="relative">
          <input
            ref={searchInputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => {
                const val = e.target.value;
                setSearchQuery(val);
                setShowSearchTagDropdown(true);
                if (searchTagDebounceRef.current) clearTimeout(searchTagDebounceRef.current);
                searchTagDebounceRef.current = setTimeout(() => {
                    if (val.trim()) fetchTagSuggestions(val, setSearchTagSuggestions);
                    else setSearchTagSuggestions([]);
                }, 300);
            }}
            onFocus={() => { if (searchQuery.trim()) setShowSearchTagDropdown(true); }}
            placeholder="Search routes..."
            className="w-full bg-gray-800 text-gray-200 px-4 py-2.5 rounded-xl border border-gray-700 focus:outline-none focus:border-riduck-primary text-xs"
          />
          <span className="absolute right-3 top-2.5 text-gray-600 text-xs">🔍</span>
          {/* Search Tag Autocomplete Dropdown */}
          {showSearchTagDropdown && searchFilteredTags.length > 0 && (
            <div ref={searchTagDropdownRef} className="absolute left-0 right-0 mt-1 max-h-32 overflow-y-auto bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-10">
              {searchFilteredTags.map(tag => (
                <button key={tag.slug}
                    onClick={() => { onFiltersChange({ ...routeFilters, tags: [...routeFilters.tags, tag.slug] }); setSearchQuery(''); setShowSearchTagDropdown(false); }}
                    className="w-full text-left px-2.5 py-1.5 text-[11px] text-gray-300 hover:bg-gray-700 hover:text-white flex justify-between"
                >
                  <span>#{tag.name}</span>
                  <span className="flex items-center gap-1.5">
                    {tag.similarity != null && <span className="text-[9px] text-gray-500">{Math.round(tag.similarity * 100)}%</span>}
                    <span className="text-[9px] text-gray-600">{tag.count}</span>
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Selected Tag Chips (visible outside filter panel) */}
        {routeFilters && routeFilters.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {routeFilters.tags.map(slug => (
              <span key={slug} className="inline-flex items-center gap-0.5 bg-riduck-primary/15 border border-riduck-primary/30 text-riduck-primary text-[10px] px-2 py-0.5 rounded-full">
                {allTags.find(t => t.slug === slug)?.name || slug}
                <button onClick={() => onFiltersChange({ ...routeFilters, tags: routeFilters.tags.filter(t => t !== slug) })} className="hover:text-white ml-0.5">
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-2.5 w-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
              </span>
            ))}
          </div>
        )}

        {/* Collapsible Filter Panel */}
        {isFilterOpen && routeFilters && (
          <div className="mt-3 p-3 bg-gray-800/50 border border-gray-700/50 rounded-xl space-y-3">
            {/* Distance */}
            <div>
              <label className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">거리 (km)</label>
              <div className="flex items-center gap-2 mt-1">
                <input type="number" placeholder="최소"
                    value={routeFilters.minDistance}
                    onChange={e => onFiltersChange({ ...routeFilters, minDistance: e.target.value })}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-2.5 py-1.5 text-[11px] text-white placeholder-gray-600 focus:outline-none focus:border-riduck-primary"
                />
                <span className="text-gray-600 text-[10px]">~</span>
                <input type="number" placeholder="최대"
                    value={routeFilters.maxDistance}
                    onChange={e => onFiltersChange({ ...routeFilters, maxDistance: e.target.value })}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-2.5 py-1.5 text-[11px] text-white placeholder-gray-600 focus:outline-none focus:border-riduck-primary"
                />
              </div>
            </div>

            {/* Elevation */}
            <div>
              <label className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">획득고도 (m)</label>
              <div className="flex items-center gap-2 mt-1">
                <input type="number" placeholder="최소"
                    value={routeFilters.minElevation}
                    onChange={e => onFiltersChange({ ...routeFilters, minElevation: e.target.value })}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-2.5 py-1.5 text-[11px] text-white placeholder-gray-600 focus:outline-none focus:border-riduck-primary"
                />
                <span className="text-gray-600 text-[10px]">~</span>
                <input type="number" placeholder="최대"
                    value={routeFilters.maxElevation}
                    onChange={e => onFiltersChange({ ...routeFilters, maxElevation: e.target.value })}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-2.5 py-1.5 text-[11px] text-white placeholder-gray-600 focus:outline-none focus:border-riduck-primary"
                />
              </div>
            </div>

            {/* Tags */}
            <div>
              <label className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">태그</label>
              {routeFilters.tags.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1 mb-1.5">
                  {routeFilters.tags.map(slug => (
                    <span key={slug} className="inline-flex items-center gap-0.5 bg-riduck-primary/15 border border-riduck-primary/30 text-riduck-primary text-[10px] px-2 py-0.5 rounded-full">
                      {allTags.find(t => t.slug === slug)?.name || slug}
                      <button onClick={() => onFiltersChange({ ...routeFilters, tags: routeFilters.tags.filter(t => t !== slug) })} className="hover:text-white ml-0.5">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-2.5 w-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                      </button>
                    </span>
                  ))}
                </div>
              )}
              <div className="relative mt-1">
                <input ref={tagInputRef} type="text" placeholder="태그 검색..."
                    value={tagQuery}
                    onChange={e => {
                        const val = e.target.value;
                        setTagQuery(val);
                        setShowTagDropdown(true);
                        if (tagDebounceRef.current) clearTimeout(tagDebounceRef.current);
                        tagDebounceRef.current = setTimeout(() => fetchTagSuggestions(val, setTagSuggestions), 300);
                    }}
                    onFocus={() => { setShowTagDropdown(true); if (!tagSuggestions.length) fetchTagSuggestions(tagQuery, setTagSuggestions); }}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-2.5 py-1.5 text-[11px] text-white placeholder-gray-600 focus:outline-none focus:border-riduck-primary"
                />
                {showTagDropdown && filteredTags.length > 0 && (
                  <div ref={tagDropdownRef} className="absolute left-0 right-0 mt-1 max-h-32 overflow-y-auto bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-10">
                    {filteredTags.map(tag => (
                      <button key={tag.slug}
                          onClick={() => { onFiltersChange({ ...routeFilters, tags: [...routeFilters.tags, tag.slug] }); setTagQuery(''); setShowTagDropdown(false); }}
                          className="w-full text-left px-2.5 py-1.5 text-[11px] text-gray-300 hover:bg-gray-700 hover:text-white flex justify-between"
                      >
                        <span>{tag.name}</span>
                        <span className="flex items-center gap-1.5">
                          {tag.similarity != null && <span className="text-[9px] text-gray-500">{Math.round(tag.similarity * 100)}%</span>}
                          <span className="text-[9px] text-gray-600">{tag.count}</span>
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Reset */}
            {hasActiveFilters && (
              <button
                  onClick={() => onFiltersChange({ ...routeFilters, minDistance: '', maxDistance: '', minElevation: '', maxElevation: '', tags: [] })}
                  className="w-full text-[10px] text-gray-500 hover:text-gray-300 py-1 transition-colors"
              >
                  필터 초기화
              </button>
            )}
          </div>
        )}
        
        {/* Tab Navigation */}
        <div className="flex gap-1 text-[10px] mt-3">
            {[
              { key: 'all', label: 'All Routes' },
              { key: 'my', label: 'My Routes' },
              { key: 'favorites', label: 'Favorites' },
            ].map(tab => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex-1 px-2 py-1.5 rounded-lg border transition-all ${
                    activeTab === tab.key
                    ? 'bg-riduck-primary/20 text-riduck-primary border-riduck-primary/50 font-bold'
                    : 'bg-gray-800 text-gray-500 border-gray-700 hover:bg-gray-700'
                }`}
              >
                {tab.label}
              </button>
            ))}
        </div>
      </div>

      {/* 2. Scrollable Content */}
      <div 
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto p-4 custom-scrollbar"
      >
          {error && (
            <div className="p-4 mb-4 bg-red-500/10 border border-red-500/50 rounded-xl text-center">
                <p className="text-xs text-red-400 mb-2">{error}</p>
                <button 
                    onClick={() => fetchData(1, true)}
                    className="text-[10px] font-bold bg-red-500/20 hover:bg-red-500/30 text-red-300 px-3 py-1 rounded-lg border border-red-500/30 transition-all"
                >
                    RETRY CONNECTION
                </button>
            </div>
          )}

          {/* Tab: All Routes */}
          {activeTab === 'all' && (
            <div>
                {loading && publicRoutes.length === 0 ? (
                   <div className="flex justify-center p-4"><div className="animate-spin h-5 w-5 border-2 border-riduck-primary rounded-full border-t-transparent"></div></div>
                ) : publicRoutes.length === 0 && !error ? (
                   <div className="flex flex-col items-center justify-center text-center p-6 border-2 border-dashed border-gray-800 rounded-xl bg-gray-900/30">
                      <div className="w-8 h-8 bg-gray-800 rounded-full flex items-center justify-center mb-2 text-gray-600">🌍</div>
                      <p className="text-xs text-gray-600">No routes found.</p>
                   </div>
                ) : (
                   <div className="space-y-3">
                      {publicRoutes.map(route => <React.Fragment key={`pub-${route.id}`}>{renderRouteCard(route, false)}</React.Fragment>)}
                   </div>
                )}
            </div>
          )}

          {/* Tab: My Routes */}
          {activeTab === 'my' && (
            <div>
                {!user ? (
                   <div className="flex flex-col items-center justify-center text-center p-6 border-2 border-dashed border-gray-800 rounded-xl bg-gray-900/30">
                      <p className="text-xs text-gray-500 mb-2">Login to save your routes.</p>
                   </div>
                ) : loading && myRoutes.length === 0 ? (
                   <div className="flex justify-center p-4"><div className="animate-spin h-5 w-5 border-2 border-riduck-primary rounded-full border-t-transparent"></div></div>
                ) : myRoutes.length === 0 && !error ? (
                   <div className="flex flex-col items-center justify-center text-center p-6 border-2 border-dashed border-gray-800 rounded-xl bg-gray-900/30">
                      <div className="w-8 h-8 bg-gray-800 rounded-full flex items-center justify-center mb-2 text-gray-600">👤</div>
                      <p className="text-xs text-gray-600">No personal routes found.</p>
                   </div>
                ) : (
                   <div className="space-y-3">
                      {myRoutes.map(route => <React.Fragment key={`my-${route.id}`}>{renderRouteCard(route, true)}</React.Fragment>)}
                   </div>
                )}
            </div>
          )}

          {/* Tab: Favorites (Coming Soon) */}
          {activeTab === 'favorites' && (
            <div className="flex flex-col items-center justify-center text-center p-8 mt-4 border-2 border-dashed border-gray-800 rounded-xl bg-gray-900/30">
                <div className="w-10 h-10 bg-gray-800 rounded-full flex items-center justify-center mb-3 text-gray-600 text-lg">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                    </svg>
                </div>
                <p className="text-xs text-gray-500 font-medium mb-1">Coming Soon</p>
                <p className="text-[10px] text-gray-600">Save your favorite routes for quick access.</p>
            </div>
          )}

          {/* Infinite Scroll Loader */}
          {loadingMore && (
              <div className="py-4 flex justify-center">
                  <div className="animate-spin h-5 w-5 border-2 border-riduck-primary rounded-full border-t-transparent"></div>
              </div>
          )}
          {!loading && !loadingMore && activeTab !== 'favorites' && (
              ((activeTab === 'my' && !hasMoreMy && myRoutes.length > 0) || (activeTab === 'all' && !hasMorePublic && publicRoutes.length > 0)) && (
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
