import React from 'react'
import BikeRoutePlanner from './components/BikeRoutePlanner'
import Login from './components/Login'

function App() {
  return (
    <div className="min-h-screen bg-riduck-dark text-white p-4 md:p-10 flex flex-col items-center">
      <header className="w-full max-w-6xl mb-8 flex justify-between items-center">
        <h1 className="text-3xl md:text-4xl font-bold text-riduck-primary">
          Riduck Route Planner <span className="text-xs text-gray-500 border border-gray-600 px-2 py-1 rounded ml-2">ALPHA</span>
        </h1>
        <div className="flex items-center gap-4">
          <button 
            className="w-8 h-8 rounded-full border border-gray-600 text-gray-400 hover:text-white hover:border-white flex items-center justify-center transition-colors"
            onClick={() => alert("1. 지도 클릭: 경유지 추가\n2. 마커 클릭: 경유지 삭제\n3. Save: 코스 저장 (로그인 필요)")}
          >
            ?
          </button>
          <Login />
        </div>
      </header>
      
      <main className="w-full max-w-6xl flex-grow flex flex-col">
        <div className="flex-1 w-full h-[70vh] rounded-xl overflow-hidden border border-gray-800 shadow-2xl relative">
          <BikeRoutePlanner />
        </div>
      </main>
    </div>
  )
}

export default App
