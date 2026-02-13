import React, { useState } from 'react'
import { Routes, Route, useParams, useNavigate } from 'react-router-dom'
import BikeRoutePlanner from './components/BikeRoutePlanner'
import Login from './components/Login'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />} />
      <Route path="/route/:routeId" element={<Layout />} />
    </Routes>
  );
}

function Layout() {
  const { routeId } = useParams();
  const [routeName, setRouteName] = useState('');
  const [isEditingName, setIsEditingName] = useState(false);

  return (
    <div className="h-screen bg-riduck-dark text-white flex flex-col overflow-hidden">
      {/* Header */}
      <header className="relative h-14 md:h-16 px-4 md:px-6 border-b border-gray-800 bg-gray-900 flex justify-between items-center z-30 shadow-md shrink-0 gap-4">
        <div className="flex items-center gap-4 overflow-hidden flex-1 mr-4">
            <div className="flex items-center gap-2 md:gap-3 shrink-0">
                <h1 className="text-lg md:text-2xl font-bold text-riduck-primary tracking-tight truncate">
                Riduck <span className="text-white font-light">Planner</span>
                </h1>
                <span className="text-[10px] text-gray-500 border border-gray-700 px-1.5 py-0.5 rounded uppercase tracking-wider hidden sm:inline-block">Alpha</span>
            </div>
            
            <div className="h-6 w-px bg-gray-700 hidden md:block shrink-0"></div>

            {/* Route Name */}
            <div 
                className="group flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-gray-800 transition-colors cursor-pointer min-w-0"
                onClick={() => setIsEditingName(true)}
            >
                {isEditingName ? (
                    <input 
                        autoFocus
                        type="text" 
                        value={routeName}
                        placeholder="Untitled Route"
                        onChange={(e) => setRouteName(e.target.value)}
                        onBlur={() => setIsEditingName(false)}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                                setIsEditingName(false);
                            }
                        }}
                        className="bg-transparent text-white font-bold text-base md:text-lg outline-none w-full min-w-[120px]"
                    />
                ) : (
                    <>
                        <span className={`font-bold text-base md:text-lg truncate ${!routeName ? 'text-gray-500' : 'text-white'}`}>
                            {routeName || 'Untitled Route'}
                        </span>
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5 text-gray-600 group-hover:text-gray-400 transition-colors shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                        </svg>
                    </>
                )}
            </div>
        </div>

        <div className="flex items-center gap-3 md:gap-4 shrink-0">
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
        <BikeRoutePlanner 
            routeName={routeName} 
            setRouteName={setRouteName} 
            initialRouteId={routeId}
        />
      </main>
    </div>
  )
}

export default App