import React, { useState } from 'react';

const SearchPanel = () => {
  const [searchQuery, setSearchQuery] = useState('');

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
            placeholder="Search routes..." 
            className="w-full bg-gray-800 text-white px-4 py-2.5 rounded-xl border border-gray-700 focus:outline-none focus:border-riduck-primary text-xs"
          />
          <span className="absolute right-3 top-2.5 text-gray-500 text-xs">🔍</span>
        </div>
        
        {/* Search Scope Filter */}
        <div className="flex gap-2 text-[10px] mt-3">
            <span className="px-2 py-1 bg-riduck-primary/20 text-riduck-primary rounded border border-riduck-primary/30 cursor-pointer">All</span>
            <span className="px-2 py-1 bg-gray-800 text-gray-400 rounded border border-gray-700 hover:bg-gray-700 cursor-pointer">My Routes</span>
            <span className="px-2 py-1 bg-gray-800 text-gray-400 rounded border border-gray-700 hover:bg-gray-700 cursor-pointer">Open Courses</span>
        </div>
      </div>

      {/* 2. Scrollable Content */}
      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
          {/* Section: My Routes */}
          <div className="mb-4">
              <h3 className="text-[10px] font-bold text-gray-500 uppercase mb-2 px-1">My Routes</h3>
              <div className="flex flex-col items-center justify-center text-center p-6 border-2 border-dashed border-gray-800 rounded-xl bg-gray-900/30">
                <div className="w-8 h-8 bg-gray-800 rounded-full flex items-center justify-center mb-2 text-gray-600">👤</div>
                <p className="text-xs text-gray-600">No personal routes saved.</p>
              </div>
          </div>

          {/* Section: Open Courses */}
          <div>
              <h3 className="text-[10px] font-bold text-gray-500 uppercase mb-2 px-1">Open Courses</h3>
              <div className="flex flex-col items-center justify-center text-center p-6 border-2 border-dashed border-gray-800 rounded-xl bg-gray-900/30">
                <div className="w-8 h-8 bg-gray-800 rounded-full flex items-center justify-center mb-2 text-gray-600">🌍</div>
                <p className="text-xs text-gray-600">Search to find public courses.</p>
              </div>
          </div>
      </div>
    </div>
  );
};

export default SearchPanel;