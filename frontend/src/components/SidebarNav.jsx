import React from 'react';

const SidebarNav = ({ isMenuOpen, isSearchOpen, onToggleMenu, onToggleSearch }) => {
  return (
    <div className="hidden md:flex w-16 h-full bg-gray-900 border-r border-gray-800 flex-col items-center py-4 shrink-0 z-50">
      {/* Menu Toggle */}
      <button 
        onClick={onToggleMenu}
        className={`p-3 rounded-xl mb-4 transition-colors ${isMenuOpen ? 'bg-riduck-primary text-white shadow-lg shadow-riduck-primary/20' : 'text-gray-400 hover:text-white hover:bg-gray-800'}`}
        title="Menu"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
        </svg>
      </button>

      {/* Search Toggle */}
      <button 
        onClick={onToggleSearch}
        className={`p-3 rounded-xl mb-4 transition-colors ${isSearchOpen ? 'bg-riduck-primary text-white shadow-lg shadow-riduck-primary/20' : 'text-gray-400 hover:text-white hover:bg-gray-800'}`}
        title="Library"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.58 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.58 4 8 4s8-1.79 8-4M4 7c0-2.21 3.58-4 8-4s8 1.79 8 4" />
        </svg>
      </button>
    </div>
  );
};

export default SidebarNav;