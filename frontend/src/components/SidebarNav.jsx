import React from 'react';
import { useAuth } from '../AuthContext';

const SidebarNav = ({
  isMenuOpen,
  isSearchOpen,
  onToggleMenu,
  onToggleSearch,
  onNewRoute,
  isClean,
  onImportGPX,
  onExportGPX,
  isNearbyMode,
  onToggleNearby,
  isWaypointMode,
  onToggleWaypoint
}) => {
  const { isAdmin } = useAuth();
  
  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      onImportGPX(file);
      e.target.value = '';
    }
  };

  return (
    <div className="hidden md:flex w-16 h-full bg-gray-900 border-r border-gray-800 flex-col items-center py-6 shrink-0 z-50 gap-2">
      {/* Menu Toggle */}
      <button
        onClick={onToggleMenu}
        className={`p-3 rounded-xl transition-colors ${isMenuOpen ? 'bg-routy-primary text-white shadow-lg shadow-routy-primary/20' : 'text-gray-400 hover:text-white hover:bg-gray-800'}`}
        title="Menu"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
        </svg>
      </button>

      {/* Search Toggle */}
      <button
        onClick={onToggleSearch}
        className={`p-3 rounded-xl transition-colors ${isSearchOpen ? 'bg-routy-primary text-white shadow-lg shadow-routy-primary/20' : 'text-gray-400 hover:text-white hover:bg-gray-800'}`}
        title="Library"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.58 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.58 4 8 4s8-1.79 8-4M4 7c0-2.21 3.58-4 8-4s8 1.79 8 4" />
        </svg>
      </button>

      {/* Nearby Mode Toggle */}
      <button
        onClick={onToggleNearby}
        className={`p-3 rounded-xl transition-colors ${isNearbyMode ? 'bg-routy-primary text-white shadow-lg shadow-routy-primary/20' : 'text-gray-400 hover:text-white hover:bg-gray-800'}`}
        title="Explore Nearby"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
        </svg>
      </button>

      {/* Waypoint Mode Toggle (Admin Only) */}
      {isAdmin && (
        <button
          onClick={onToggleWaypoint}
          className={`p-3 rounded-xl transition-colors ${isWaypointMode ? 'bg-routy-primary text-white shadow-lg shadow-routy-primary/20' : 'text-gray-400 hover:text-white hover:bg-gray-800'}`}
          title="Waypoints (Admin)"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        </button>
      )}

      {/* Divider */}
      <div className="w-8 h-px bg-gray-800 my-2"></div>

      {/* New Route Button */}
      <button
        onClick={onNewRoute}
        disabled={isClean}
        className={`p-3 rounded-xl transition-all ${isClean ? 'text-gray-700 cursor-not-allowed opacity-50' : 'text-gray-400 hover:text-white hover:bg-gray-800 hover:scale-110 active:scale-95'}`}
        title="New Route"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
      </button>

      {/* Import GPX/TCX */}
      <label className="flex items-center justify-center cursor-pointer p-3 rounded-xl text-gray-400 hover:text-white hover:bg-gray-800 transition-colors" title="Import GPX/TCX">
        <input type="file" accept=".gpx,.tcx" className="hidden" onChange={handleFileChange} />
        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
        </svg>
      </label>

      {/* Export GPX/TCX */}
      <button
        onClick={onExportGPX}
        disabled={isClean}
        className={`flex items-center justify-center p-3 rounded-xl transition-colors ${isClean ? 'text-gray-700 cursor-not-allowed opacity-50' : 'text-gray-400 hover:text-white hover:bg-gray-800'}`}
        title="Export GPX/TCX"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
        </svg>
      </button>
    </div>
  );
};

export default SidebarNav;
