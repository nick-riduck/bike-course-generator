import React from 'react';

const SidebarNav = ({ isMenuOpen, isSearchOpen, onToggleMenu, onToggleSearch }) => {
  return (
    <div className="w-16 h-full bg-gray-900 border-r border-gray-800 flex flex-col items-center py-4 shrink-0 z-50">
      {/* Menu Toggle */}
      <button 
        onClick={onToggleMenu}
        className={`p-3 rounded-xl mb-4 transition-colors ${isMenuOpen ? 'bg-riduck-primary text-white shadow-lg shadow-riduck-primary/20' : 'text-gray-400 hover:text-white hover:bg-gray-800'}`}
        title="Menu"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {/* Search Toggle */}
      <button 
        onClick={onToggleSearch}
        className={`p-3 rounded-xl mb-4 transition-colors ${isSearchOpen ? 'bg-riduck-primary text-white shadow-lg shadow-riduck-primary/20' : 'text-gray-400 hover:text-white hover:bg-gray-800'}`}
        title="Search"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      </button>
    </div>
  );
};

export default SidebarNav;