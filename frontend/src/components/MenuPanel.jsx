import React, { useState } from 'react';

const MenuPanel = ({ 
  history, 
  onUndo, 
  onRedo, 
  onClear, 
  onSave, 
  onDownloadGPX, 
  sections,
  onPointRemove,
  onSplitSection,
  onSectionHover,
  onSectionDelete,
  onSectionMerge,
  onSectionRename,
  onSectionDownload,
  isMockMode,
  setIsMockMode
}) => {
  const [editingSectionId, setEditingSectionId] = useState(null);
  const [tempName, setTempName] = useState('');

  const handleStartRename = (section) => {
    setEditingSectionId(section.id);
    setTempName(section.name);
  };

  const handleFinishRename = (sIdx) => {
    if (tempName.trim()) {
      onSectionRename(sIdx, tempName.trim());
    }
    setEditingSectionId(null);
  };

  return (
    <div className="w-80 h-full bg-gray-900 border-r border-gray-800 flex flex-col animate-fadeIn shadow-xl z-40">
      {/* 1. Header */}
      <div className="p-4 border-b border-gray-800 flex justify-between items-center bg-gray-900/50 backdrop-blur-md">
        <h2 className="font-bold text-white text-lg tracking-tight">Route Planner</h2>
      </div>

      {/* 2. Scrollable Content */}
      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar flex flex-col gap-6">
        {/* Mock Mode Toggle */}
        <div className="flex items-center justify-between bg-gray-800/30 p-4 rounded-2xl border border-gray-800 shadow-inner">
          <div>
              <p className="text-sm font-bold text-gray-200">Mock Mode</p>
              <p className="text-[10px] text-gray-500 font-medium">Fast straight lines for testing</p>
          </div>
          <button 
            onClick={() => setIsMockMode(!isMockMode)} 
            className={`w-11 h-6 rounded-full relative transition-all duration-300 ${isMockMode ? 'bg-riduck-primary' : 'bg-gray-700'}`}
          >
            <div className={`absolute top-1 w-4 h-4 bg-white rounded-full shadow-lg transition-all duration-300 transform ${isMockMode ? 'translate-x-6' : 'translate-x-1'}`} />
          </button>
        </div>

        {/* Sections & Points List */}
        <div className="space-y-8">
            {sections.map((section, sIdx) => {
              const secDist = section.segments.reduce((a, b) => a + (b.distance || 0), 0);
              const secAsc = section.segments.reduce((a, b) => a + (b.ascent || 0), 0);
              
              return (
                <div 
                  key={section.id} 
                  className="group/section space-y-3 transition-all"
                  onMouseEnter={() => onSectionHover && onSectionHover(sIdx)}
                  onMouseLeave={() => onSectionHover && onSectionHover(null)}
                >
                  {/* Section Header Card */}
                  <div className="bg-gray-800/40 border border-gray-700/50 rounded-2xl p-3 shadow-sm hover:border-gray-600 transition-all">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2 flex-1 min-w-0">
                        <div className="w-2.5 h-2.5 rounded-full shadow-sm shrink-0" style={{ backgroundColor: section.color }}></div>
                        {editingSectionId === section.id ? (
                          <input 
                            autoFocus
                            className="bg-gray-900 text-white text-xs font-bold px-2 py-1 rounded border border-riduck-primary focus:outline-none w-full"
                            value={tempName}
                            onChange={(e) => setTempName(e.target.value)}
                            onBlur={() => handleFinishRename(sIdx)}
                            onKeyDown={(e) => e.key === 'Enter' && handleFinishRename(sIdx)}
                          />
                        ) : (
                          <h3 
                            className="text-sm font-bold text-gray-200 tracking-tight truncate cursor-pointer hover:text-white transition-colors"
                            onClick={() => handleStartRename(section)}
                          >
                            {section.name}
                          </h3>
                        )}
                      </div>
                      <div className="flex flex-col items-end">
                        <span className="text-[10px] text-gray-400 font-mono font-bold">
                          {secDist.toFixed(1)}km
                        </span>
                        <span className="text-[9px] text-gray-600 font-mono">
                          +{Math.round(secAsc)}m
                        </span>
                      </div>
                    </div>

                    {/* Section Actions Toolbar */}
                    <div className="flex items-center justify-end gap-1 pt-1 border-t border-gray-700/30 mt-2">
                      <button 
                        onClick={() => onSectionDownload(sIdx)}
                        className="p-1.5 text-gray-500 hover:text-blue-400 hover:bg-blue-400/10 rounded-lg transition-all"
                        title="Download this section as GPX"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                        </svg>
                      </button>
                      
                      {/* Merge UP (First section can't merge up) */}
                      {sIdx > 0 && (
                        <button 
                          onClick={() => onSectionMerge(sIdx - 1)}
                          className="p-1.5 text-gray-500 hover:text-green-400 hover:bg-green-400/10 rounded-lg transition-all"
                          title="Merge with section above"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" style={{ transform: 'rotate(180deg)' }}>
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13.172 9l2.586 2.586-2.586 2.586M9 13.172l-2.586-2.586 2.586-2.586M15 19l-7-7 7-7" />
                          </svg>
                        </button>
                      )}

                      {/* Merge DOWN (Last section can't merge down) */}
                      {sIdx < sections.length - 1 && (
                        <button 
                          onClick={() => onSectionMerge(sIdx)}
                          className="p-1.5 text-gray-500 hover:text-green-400 hover:bg-green-400/10 rounded-lg transition-all"
                          title="Merge with section below"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13.172 9l2.586 2.586-2.586 2.586M9 13.172l-2.586-2.586 2.586-2.586M15 19l-7-7 7-7" />
                          </svg>
                        </button>
                      )}

                      <button 
                        onClick={() => onSectionDelete(sIdx)}
                        className="p-1.5 text-gray-500 hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-all"
                        title="Delete entire section"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  </div>
                  
                  {/* Points inside section */}
                  <div className="flex flex-col gap-2 pl-2 border-l-2 border-gray-800/50 ml-1.5 mt-2">
                    {section.points.map((p, pIdx) => (
                      <div key={p.id} className="group flex items-center gap-3 bg-gray-800/20 p-2.5 rounded-xl border border-transparent hover:border-gray-700 hover:bg-gray-800/40 transition-all">
                        <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold text-white shadow-sm`} style={{ backgroundColor: section.color }}>
                          {pIdx + 1}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-[10px] text-gray-500 font-mono truncate group-hover:text-gray-300 transition-colors">
                            {p.lat.toFixed(4)}, {p.lng.toFixed(4)}
                          </p>
                        </div>
                        
                        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-all">
                          {pIdx > 0 && (
                            <button 
                              onClick={() => onSplitSection(sIdx, pIdx)}
                              className="p-1 text-gray-500 hover:text-blue-400 hover:bg-blue-400/10 rounded-lg transition-colors"
                              title="Split Section Here"
                            >
                              <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.121 14.121L19 19m-7-7l7-7m-7 7l-2.879 2.879M12 12L9.121 9.121m0 5.758L5 19m0-14l4.121 4.121" />
                              </svg>
                            </button>
                          )}
                          <button 
                            onClick={(e) => onPointRemove(sIdx, pIdx, e)}
                            className="p-1 text-gray-500 hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-colors"
                            title="Remove Point"
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
            
            {sections.every(s => s.points.length === 0) && (
               <div className="text-sm text-gray-500 italic text-center py-12 border-2 border-dashed border-gray-800 rounded-2xl bg-gray-900/50">
                  <div className="text-2xl mb-2 opacity-20">🗺️</div>
                  Click on map to start planning
              </div>
            )}
        </div>
      </div>

      {/* 3. Footer Actions */}
      <div className="p-4 border-t border-gray-800 bg-gray-900/95 backdrop-blur-md space-y-4 shadow-2xl">
        {/* Editor Tools */}
        <div className="grid grid-cols-3 gap-2">
          <button 
              onClick={onUndo} 
              disabled={history.past.length === 0} 
              className="py-2.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white text-xs font-bold disabled:opacity-20 disabled:cursor-not-allowed transition-all active:scale-95"
          >
              Undo
          </button>
          <button 
              onClick={onRedo} 
              disabled={history.future.length === 0} 
              className="py-2.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white text-xs font-bold disabled:opacity-20 disabled:cursor-not-allowed transition-all active:scale-95"
          >
              Redo
          </button>
          <button 
              onClick={onClear} 
              className="py-2.5 rounded-xl bg-red-500/5 hover:bg-red-500/10 text-red-500/70 hover:text-red-500 text-xs font-bold transition-all border border-red-500/10 active:scale-95"
          >
              Clear
          </button>
        </div>

        {/* Save & Export */}
        {(() => {
          const hasSegments = sections.some(s => s.segments.length > 0);
          return (
            <div className="grid grid-cols-1 gap-2">
                <button 
                    onClick={onSave}
                    disabled={!hasSegments}
                    className="bg-riduck-primary hover:brightness-110 text-white py-3.5 rounded-2xl font-black text-sm shadow-lg shadow-riduck-primary/20 disabled:opacity-20 disabled:grayscale transition-all active:scale-[0.98]"
                >
                    SAVE TO CLOUD
                </button>
                <button 
                    onClick={onDownloadGPX}
                    disabled={!hasSegments}
                    className="bg-gray-800 hover:bg-gray-700 text-white py-3 rounded-2xl font-bold text-[11px] transition-all border border-gray-700/50 active:scale-[0.98]"
                >
                    DOWNLOAD ENTIRE GPX
                </button>
            </div>
          );
        })()}
      </div>
    </div>
  );
};

export default MenuPanel;