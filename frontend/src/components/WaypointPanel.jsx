import React, { useState, useEffect } from 'react';

const TYPE_LABELS = {
  convenience_store: '편의점', cafe: '카페', restaurant: '음식점', restroom: '화장실',
  water_fountain: '음수대', rest_area: '쉼터', bike_shop: '자전거샵',
  parking: '주차장', transit: '대중교통', bridge: '교량', tunnel: '터널', checkpoint: '인증센터',
  viewpoint: '뷰포인트', river: '강/하천', lake: '호수', mountain: '산', beach: '해변',
  park: '공원', nature: '자연', historic: '역사', landmark: '랜드마크', museum: '박물관',
  hospital: '병원', police: '경찰서', other: '기타',
};

const FILTER_GROUPS = [
  { label: '전체', options: [{ value: 'all', label: '모든 웨이포인트' }, { value: 'popular', label: '인기 (5+ 코스)' }] },
  { label: '보급/편의', options: ['convenience_store', 'cafe', 'restaurant', 'restroom', 'water_fountain', 'rest_area', 'bike_shop'] },
  { label: '인프라', options: ['parking', 'transit', 'bridge', 'tunnel', 'checkpoint'] },
  { label: '경관/자연', options: ['viewpoint', 'river', 'lake', 'mountain', 'beach', 'park', 'nature'] },
  { label: '문화/기타', options: ['historic', 'landmark', 'museum', 'hospital', 'police', 'other'] },
];

const WaypointPanel = ({
  onWaypointClick,
  onWaypointAdd,
  onClose
}) => {
  const [waypoints, setWaypoints] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState('all');
  // selectedId managed by parent via onWaypointClick

  useEffect(() => {
    fetchWaypoints();
  }, []);

  const fetchWaypoints = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/waypoints');
      if (res.ok) {
        const data = await res.json();
        setWaypoints(data);
      }
    } catch (e) {
      console.error("Failed to fetch waypoints:", e);
    } finally {
      setLoading(false);
    }
  };

  const filteredWaypoints = waypoints.filter(wp => {
    if (filterType === 'all') return true;
    if (filterType === 'popular') return wp.tour_count >= 5;
    return wp.type && wp.type.includes(filterType);
  });

  const stats = {
    total: waypoints.length,
    high: waypoints.filter(p => p.tour_count >= 5).length,
    mid: waypoints.filter(p => p.tour_count >= 2 && p.tour_count < 5).length,
    low: waypoints.filter(p => p.tour_count === 1).length,
  };

  return (
    <div className="w-80 h-full bg-gray-900 border-r border-gray-800 flex flex-col animate-fadeIn shadow-xl z-40 relative">
      {/* Header */}
      <div className="p-4 border-b border-gray-800 flex justify-between items-center bg-gray-900/50 backdrop-blur-md">
        <h2 className="font-bold text-white text-lg tracking-tight flex items-center gap-2">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-riduck-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          Waypoints
        </h2>
        <button
          onClick={onClose}
          className="p-1.5 text-gray-500 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Legend & Filter */}
      <div className="p-4 border-b border-gray-800 bg-gray-900 shrink-0">
        <div className="text-xs text-gray-400 mb-2 font-medium">등장 빈도 (총 {stats.total}개)</div>
        <div className="flex gap-4 text-[10px] text-gray-400 mb-3">
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-[#e41a1c]" /> 5+ ({stats.high})</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-[#ff7f00]" /> 2-4 ({stats.mid})</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-[#377eb8]" /> 1 ({stats.low})</span>
        </div>

        <select
          className="w-full bg-gray-800 border border-gray-700 text-white text-sm rounded-xl px-3 py-2 outline-none focus:border-riduck-primary transition-colors"
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
        >
          {FILTER_GROUPS.map(group => (
            <optgroup key={group.label} label={group.label}>
              {group.options.map(opt => {
                if (typeof opt === 'string') {
                  return <option key={opt} value={opt}>{TYPE_LABELS[opt] || opt}</option>;
                }
                return <option key={opt.value} value={opt.value}>{opt.label}</option>;
              })}
            </optgroup>
          ))}
        </select>

        {filterType !== 'all' && (
          <div className="mt-2 text-xs text-gray-500">
            {filteredWaypoints.length}개 표시 중
          </div>
        )}
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto p-3 custom-scrollbar">
        {loading ? (
          <div className="flex flex-col items-center justify-center h-32 gap-3 text-gray-500">
             <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-riduck-primary"></div>
             <p className="text-sm font-medium">Loading...</p>
          </div>
        ) : filteredWaypoints.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-gray-500 text-sm">
             해당 타입의 웨이포인트가 없습니다.
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            {filteredWaypoints.map(wp => (
              <div
                key={wp.id}
                className="group flex items-start gap-2.5 p-2.5 rounded-xl bg-gray-800/30 border border-transparent hover:border-gray-700 hover:bg-gray-800/70 transition-all cursor-pointer"
                onClick={() => onWaypointClick(wp)}
              >
                {/* Frequency dot */}
                <div
                  className="w-2 h-2 rounded-full shrink-0 mt-1.5"
                  style={{
                    backgroundColor: wp.tour_count >= 5 ? '#e41a1c' : wp.tour_count >= 2 ? '#ff7f00' : '#377eb8'
                  }}
                />

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <h3 className="text-sm font-semibold text-white truncate">{wp.name}</h3>
                  <div className="flex items-center gap-2 mt-1 text-[10px] text-gray-500">
                    <span>{wp.tour_count} 코스</span>
                    {wp.type?.length > 0 && (
                      <span className="truncate">{(TYPE_LABELS[wp.type[0]] || wp.type[0])}</span>
                    )}
                    {wp.has_images && <span title="사진 있음">📷</span>}
                  </div>
                </div>

                {/* Add button */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onWaypointAdd(wp);
                  }}
                  className="p-1 bg-riduck-primary/10 text-riduck-primary rounded-lg opacity-0 group-hover:opacity-100 transition-all hover:bg-riduck-primary hover:text-white shrink-0"
                  title="경로에 추가"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Detail Modal rendered by parent (BikeRoutePlanner) */}
    </div>
  );
};

export default WaypointPanel;
