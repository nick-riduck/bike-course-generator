import React, { useState } from 'react';

const Sidebar = ({ 
  isOpen,
  onClose,
  history, 
  onUndo, 
  onRedo, 
  onClear, 
  onSave, 
  onDownloadGPX, 
  segments,
  isMockMode,
  setIsMockMode
}) => {
  const [activeTab, setActiveTab] = useState('planner');
  const [searchQuery, setSearchQuery] = useState('');

  return (
    <>
      {/* Mobile Overlay */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/50 z-30 lg:hidden backdrop-blur-sm"
          onClick={onClose}
        />
      )}

      {/* Sidebar Container */}
      <div className={`
        fixed lg:static inset-y-0 left-0 z-40
        w-80 h-full bg-gray-900 border-r border-gray-800 flex flex-col shadow-2xl
        transform transition-transform duration-300 ease-in-out
        ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        {/* Mobile Header (Close Button) */}
        <div className="lg:hidden p-4 border-b border-gray-800 flex justify-between items-center">
            <span className="font-bold text-white uppercase tracking-widest text-xs opacity-50">Menu</span>
            <button onClick={onClose} className="text-gray-400 hover:text-white transition-colors">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
            </button>
        </div>

        {/* 1. Header & Search */}
        <div className="p-4 border-b border-gray-800">
          <div className="relative">
            <input 
              type="text" 
              placeholder="Search places..." 
              className="w-full bg-gray-800 text-white px-4 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-riduck-primary text-sm"
            />
            <span className="absolute right-3 top-2.5 text-gray-500 text-xs">🔍</span>
          </div>
        </div>

        {/* 2. Tabs */}
        <div className="flex border-b border-gray-800">
          <button 
            className={`flex-1 py-3 text-sm font-bold transition-all ${activeTab === 'planner' ? 'text-riduck-primary border-b-2 border-riduck-primary' : 'text-gray-500 hover:text-white'}`}
            onClick={() => setActiveTab('planner')}
          >
            Planner
          </button>
          <button 
            className={`flex-1 py-3 text-sm font-bold transition-all ${activeTab === 'library' ? 'text-riduck-primary border-b-2 border-riduck-primary' : 'text-gray-500 hover:text-white'}`}
            onClick={() => setActiveTab('library')}
          >
            Library
          </button>
        </div>

        {/* 3. Tab Content */}
        <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
          {activeTab === 'planner' ? (
            <div className="flex flex-col gap-6 animate-fadeIn">
              {/* ... Planner Content ... */}
              <div className="flex items-center justify-between bg-gray-800/50 p-4 rounded-xl border border-gray-800">
                <div>
                    <p className="text-sm font-bold text-white">Mock Mode</p>
                    <p className="text-[10px] text-gray-500">Enable for quick testing</p>
                </div>
                <button 
                  onClick={() => setIsMockMode(!isMockMode)} 
                  className={`w-10 h-5 rounded-full relative transition-all duration-200 ${isMockMode ? 'bg-yellow-500' : 'bg-gray-700'}`}
                >
                  <div className={`absolute top-1 w-3 h-3 bg-white rounded-full shadow-lg transition-all duration-200 ${isMockMode ? 'left-6' : 'left-1'}`} />
                </button>
              </div>

              <div className="space-y-3">
                  <h3 className="text-[10px] font-black text-gray-500 uppercase tracking-widest px-1">Route Points</h3>
                  <div className="text-sm text-gray-500 italic text-center py-8 border-2 border-dashed border-gray-800 rounded-xl bg-gray-900/50">
                      Click on map to add points
                  </div>
              </div>
            </div>
          ) : (
            <div className="flex flex-col h-full animate-fadeIn">
              {/* Library Search */}
              <div className="mb-4 space-y-2">
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
                
                {/* Search Scope Filter (Visual Only for now) */}
                <div className="flex gap-2 text-[10px]">
                    <span className="px-2 py-1 bg-riduck-primary/20 text-riduck-primary rounded border border-riduck-primary/30 cursor-pointer">All</span>
                    <span className="px-2 py-1 bg-gray-800 text-gray-400 rounded border border-gray-700 hover:bg-gray-700 cursor-pointer">My Routes</span>
                    <span className="px-2 py-1 bg-gray-800 text-gray-400 rounded border border-gray-700 hover:bg-gray-700 cursor-pointer">Open Courses</span>
                </div>
              </div>

              {/* Course List (Placeholder) */}
              <div className="flex-1 overflow-y-auto custom-scrollbar">
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
          )}
        </div>

        {/* 4. Footer Actions */}
        <div className="p-4 border-t border-gray-800 bg-gray-900/95 backdrop-blur-md space-y-3">
          {/* Editor Tools */}
          <div className="grid grid-cols-3 gap-2">
            <button 
                onClick={onUndo} 
                disabled={history.past.length === 0} 
                className="py-2.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white text-xs font-bold disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
                Undo
            </button>
            <button 
                onClick={onRedo} 
                disabled={history.future.length === 0} 
                className="py-2.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white text-xs font-bold disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
                Redo
            </button>
            <button 
                onClick={onClear} 
                className="py-2.5 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-red-500 hover:text-red-400 text-xs font-bold transition-colors border border-red-500/20"
            >
                Clear
            </button>
          </div>

          {/* Save & Export */}
          <div className="grid grid-cols-1 gap-2">
              <button 
                  onClick={onSave}
                  disabled={segments.length === 0}
                  className="bg-riduck-primary hover:bg-opacity-90 text-white py-3 rounded-xl font-black text-sm shadow-xl disabled:opacity-30 disabled:grayscale transition-all active:scale-95"
              >
                  SAVE TO CLOUD
              </button>
              <button 
                  onClick={onDownloadGPX}
                  disabled={segments.length === 0}
                  className="bg-gray-800 hover:bg-gray-700 text-white py-3 rounded-xl font-bold text-xs transition-all active:scale-95 border border-gray-700"
              >
                  DOWNLOAD GPX
              </button>
          </div>
        </div>
      </div>
    </>
  );
};

export default Sidebar;
