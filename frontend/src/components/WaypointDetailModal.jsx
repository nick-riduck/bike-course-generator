import React, { useState, useEffect, useCallback } from 'react';
import apiClient from '../utils/apiClient';

const WAYPOINT_TYPE_LABELS = {
  convenience_store: '편의점', cafe: '카페', restaurant: '음식점', restroom: '화장실',
  water_fountain: '음수대', rest_area: '쉼터', bike_shop: '자전거샵',
  parking: '주차장', transit: '대중교통', bridge: '교량', tunnel: '터널', checkpoint: '인증센터',
  viewpoint: '뷰포인트', river: '강/하천', lake: '호수', mountain: '산', beach: '해변',
  park: '공원', nature: '자연', historic: '역사', landmark: '랜드마크', museum: '박물관',
  hospital: '병원', police: '경찰서', other: '기타',
};

const CONFIDENCE_COLORS = {
  high: 'bg-green-500/20 text-green-400',
  medium: 'bg-yellow-500/20 text-yellow-400',
  low: 'bg-red-500/20 text-red-400',
};

// Fullscreen image viewer
const ImageViewer = ({ images, initialIndex, onClose }) => {
  const [index, setIndex] = useState(initialIndex);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Escape') onClose();
    if (e.key === 'ArrowLeft') setIndex(i => Math.max(0, i - 1));
    if (e.key === 'ArrowRight') setIndex(i => Math.min(images.length - 1, i + 1));
  }, [images.length, onClose]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  const src = images[index];
  const imgUrl = src.startsWith('waypoints/') ? `/storage/${src}` : src;

  return (
    <div className="fixed inset-0 z-[9999] bg-black/95 flex items-center justify-center" onClick={onClose}>
      <div className="relative w-full h-full flex items-center justify-center" onClick={e => e.stopPropagation()}>
        <img
          src={imgUrl}
          alt=""
          className="max-w-[90vw] max-h-[90vh] object-contain"
        />
        {/* Close */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-2 bg-black/50 hover:bg-black/80 rounded-full text-white transition-colors"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
        {/* Nav arrows */}
        {index > 0 && (
          <button
            onClick={() => setIndex(i => i - 1)}
            className="absolute left-4 p-2 bg-black/50 hover:bg-black/80 rounded-full text-white transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
        )}
        {index < images.length - 1 && (
          <button
            onClick={() => setIndex(i => i + 1)}
            className="absolute right-4 p-2 bg-black/50 hover:bg-black/80 rounded-full text-white transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>
        )}
        {/* Counter */}
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-black/60 text-white text-sm px-3 py-1 rounded-full">
          {index + 1} / {images.length}
        </div>
      </div>
    </div>
  );
};

const WaypointDetailModal = ({ waypointId, onClose }) => {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewerIndex, setViewerIndex] = useState(0);

  useEffect(() => {
    if (!waypointId) return;
    setLoading(true);
    apiClient.get(`/api/waypoints/${waypointId}`)
      .then(data => {
        setDetail(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [waypointId]);

  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === 'Escape' && !viewerOpen) onClose();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose, viewerOpen]);

  if (!waypointId) return null;

  const images = detail?.image_urls || [];

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="fixed inset-0 z-[101] flex items-center justify-center p-4 pointer-events-none">
        <div
          className="bg-gray-900 rounded-2xl border border-gray-700 shadow-2xl w-full max-w-lg max-h-[85vh] overflow-hidden flex flex-col pointer-events-auto animate-fadeIn"
          onClick={e => e.stopPropagation()}
        >
          {loading ? (
            <div className="flex items-center justify-center h-48">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-routy-primary"></div>
            </div>
          ) : !detail ? (
            <div className="p-6 text-gray-400 text-center">데이터를 불러올 수 없습니다.</div>
          ) : (
            <>
              {/* Images */}
              {images.length > 0 && (
                <div className="relative shrink-0">
                  <div className="flex overflow-x-auto snap-x snap-mandatory scrollbar-hide">
                    {images.map((src, i) => {
                      const imgUrl = src.startsWith('waypoints/') ? `/storage/${src}` : src;
                      return (
                        <div
                          key={i}
                          className="snap-center shrink-0 w-full h-52 cursor-pointer"
                          onClick={() => { setViewerIndex(i); setViewerOpen(true); }}
                        >
                          <img
                            src={imgUrl}
                            alt={`${detail.name} ${i + 1}`}
                            className="w-full h-full object-cover"
                            loading="lazy"
                          />
                        </div>
                      );
                    })}
                  </div>
                  {images.length > 1 && (
                    <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex gap-1.5">
                      {images.map((_, i) => (
                        <div key={i} className="w-1.5 h-1.5 rounded-full bg-white/50" />
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Content */}
              <div className="flex-1 overflow-y-auto p-5 space-y-4 custom-scrollbar">
                {/* Header */}
                <div>
                  <div className="flex items-start justify-between">
                    <h2 className="text-lg font-bold text-white leading-tight">{detail.name}</h2>
                    <button
                      onClick={onClose}
                      className="p-1 text-gray-500 hover:text-white hover:bg-gray-800 rounded-lg transition-colors shrink-0 ml-2"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                  {detail.address && (
                    <p className="text-xs text-gray-500 mt-1">{detail.address}</p>
                  )}
                </div>

                {/* Types */}
                {detail.type?.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {detail.type.map(t => (
                      <span key={t} className="px-2 py-0.5 bg-gray-800 text-gray-300 text-xs rounded-lg border border-gray-700">
                        {WAYPOINT_TYPE_LABELS[t] || t}
                      </span>
                    ))}
                  </div>
                )}

                {/* Description */}
                {detail.description && (
                  <p className="text-sm text-gray-300 leading-relaxed">{detail.description}</p>
                )}

                {/* Stats row */}
                <div className="flex items-center gap-3 text-xs">
                  <span className="flex items-center gap-1 bg-gray-800 px-2 py-1 rounded-lg text-gray-300">
                    <span className="text-orange-400">🔥</span> {detail.tour_count}개 코스 등장
                  </span>
                  {detail.confidence && (
                    <span className={`px-2 py-1 rounded-lg text-xs ${CONFIDENCE_COLORS[detail.confidence] || 'bg-gray-800 text-gray-400'}`}>
                      {detail.confidence === 'high' ? '정확도 높음' : detail.confidence === 'medium' ? '정확도 중간' : '정확도 낮음'}
                    </span>
                  )}
                  {detail.is_verified && (
                    <span className="px-2 py-1 bg-blue-500/20 text-blue-400 rounded-lg">검증됨</span>
                  )}
                </div>

                {/* Nearby Landmarks */}
                {detail.nearby_landmarks?.length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold text-gray-400 mb-1.5 uppercase tracking-wider">주변 랜드마크</h3>
                    <div className="flex flex-wrap gap-1.5">
                      {detail.nearby_landmarks.map((lm, i) => (
                        <span key={i} className="px-2 py-0.5 bg-gray-800/60 text-gray-400 text-xs rounded-lg">
                          {lm}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Tips */}
                {detail.tips?.length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold text-gray-400 mb-1.5 uppercase tracking-wider">사용자 팁</h3>
                    <div className="space-y-2">
                      {detail.tips.map((tip, i) => (
                        <div key={i} className="bg-gray-800/40 rounded-lg p-3 border border-gray-800">
                          <p className="text-xs text-gray-300 leading-relaxed">{tip.text}</p>
                          {tip.author && (
                            <p className="text-[10px] text-gray-500 mt-1">— {tip.author}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Coordinates */}
                <div className="text-[10px] text-gray-600 pt-2 border-t border-gray-800">
                  {detail.lat?.toFixed(6)}, {detail.lng?.toFixed(6)}
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Fullscreen Image Viewer */}
      {viewerOpen && images.length > 0 && (
        <ImageViewer
          images={images}
          initialIndex={viewerIndex}
          onClose={() => setViewerOpen(false)}
        />
      )}
    </>
  );
};

export default WaypointDetailModal;
