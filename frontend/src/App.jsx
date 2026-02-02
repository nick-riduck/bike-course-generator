import React from 'react'
import BikeRoutePlanner from './components/BikeRoutePlanner'

function App() {
  return (
    <div className="min-h-screen bg-riduck-dark text-white p-4 md:p-10 flex flex-col items-center">
      <header className="w-full max-w-6xl mb-8 flex justify-between items-center">
        <h1 className="text-3xl md:text-4xl font-bold text-riduck-primary">
          Riduck Route Planner <span className="text-xs text-gray-500 border border-gray-600 px-2 py-1 rounded ml-2">ALPHA</span>
        </h1>
        <div className="text-sm text-gray-400">
          User: 7267
        </div>
      </header>
      
      <main className="w-full max-w-6xl grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Map (Span 2) */}
        <div className="lg:col-span-2">
          <BikeRoutePlanner />
        </div>

        {/* Right Column: Controls & Info */}
        <div className="flex flex-col gap-4">
          {/* Action Card */}
          <div className="p-5 bg-riduck-card rounded-xl border border-gray-800 shadow-lg flex-1 flex flex-col justify-between">
            <div>
              <h2 className="text-lg font-semibold mb-4 text-riduck-primary">Route Guide</h2>
              <div className="space-y-4 text-sm text-gray-300">
                <div className="flex items-start gap-3">
                  <div className="w-6 h-6 rounded-full bg-riduck-flat flex-shrink-0 flex items-center justify-center text-[10px] text-black font-bold">1</div>
                  <p>지도에서 <span className="text-white font-bold">출발 지점</span>을 클릭하세요.</p>
                </div>
                <div className="flex items-start gap-3">
                  <div className="w-6 h-6 rounded-full bg-riduck-uphill flex-shrink-0 flex items-center justify-center text-[10px] text-black font-bold">2</div>
                  <p>지도에서 <span className="text-white font-bold">도착 지점</span>을 클릭하세요.</p>
                </div>
                <div className="flex items-start gap-3">
                  <div className="w-6 h-6 rounded-full bg-riduck-primary flex-shrink-0 flex items-center justify-center text-[10px] text-white font-bold">3</div>
                  <p>경로가 생성되면 <span className="text-riduck-primary font-bold">거리와 소요 시간</span>이 표시됩니다.</p>
                </div>
              </div>
            </div>
            
            <button 
              className="mt-8 w-full py-4 bg-riduck-primary hover:bg-opacity-90 text-white font-extrabold rounded-xl transition-all shadow-lg active:scale-95 flex items-center justify-center gap-2"
              onClick={() => window.location.reload()}
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clipRule="evenodd" />
              </svg>
              초기화 후 다시 그리기
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}

export default App
