import React from 'react'
import BikeRoutePlanner from './components/BikeRoutePlanner'
import Login from './components/Login'

function App() {
  return (
    <div className="h-screen bg-riduck-dark text-white flex flex-col overflow-hidden">
      {/* Header */}
      <header className="h-14 md:h-16 px-4 md:px-6 border-b border-gray-800 bg-gray-900 flex justify-between items-center z-30 shadow-md shrink-0">
        <div className="flex items-center gap-2 md:gap-3 overflow-hidden">
            <h1 className="text-lg md:text-2xl font-bold text-riduck-primary tracking-tight truncate">
            Riduck <span className="text-white font-light">Planner</span>
            </h1>
            <span className="text-[10px] text-gray-500 border border-gray-700 px-1.5 py-0.5 rounded uppercase tracking-wider hidden sm:inline-block">Alpha</span>
        </div>
        
        <div className="flex items-center gap-4">
          <button 
            className="w-8 h-8 rounded-full border border-gray-600 text-gray-400 hover:text-white hover:border-white flex items-center justify-center transition-colors text-sm font-bold"
            onClick={() => alert("1. Click map to add points\n2. Click marker to remove\n3. Use sidebar to save/load")}
          >
            ?
          </button>
          <Login />
        </div>
      </header>
      
      {/* Main Content (Full Screen) */}
      <main className="flex-1 relative overflow-hidden">
        <BikeRoutePlanner />
      </main>
    </div>
  )
}

export default App