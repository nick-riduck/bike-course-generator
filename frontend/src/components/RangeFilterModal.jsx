import React, { useState, useRef, useCallback, useEffect } from 'react';

const CONFIGS = {
  distance: { label: '거리', unit: 'km', step: 20, maxFinite: 300 },
  elevation: { label: '획고', unit: 'm', step: 200, maxFinite: 3000 },
};

const buildSteps = (cfg) => {
  const arr = [];
  for (let i = 0; i <= cfg.maxFinite; i += cfg.step) arr.push(i);
  arr.push(Infinity);
  return arr;
};

// Find nearest step index for a given value
const valToNearestIdx = (steps, val) => {
  if (val === Infinity || val == null) return steps.length - 1;
  if (val <= 0) return 0;
  let best = 0;
  let bestDist = Math.abs(steps[0] - val);
  for (let i = 1; i < steps.length; i++) {
    const d = steps[i] === Infinity ? Infinity : Math.abs(steps[i] - val);
    if (d < bestDist) { best = i; bestDist = d; }
  }
  return best;
};

const RangeSlider = ({ config, minVal, maxVal, onMinChange, onMaxChange }) => {
  const steps = buildSteps(config);
  const trackRef = useRef(null);
  const dragging = useRef(null);

  const [editingField, setEditingField] = useState(null);
  const [inputValue, setInputValue] = useState('');

  const minIdx = valToNearestIdx(steps, minVal);
  const maxIdx = valToNearestIdx(steps, maxVal);
  // Ensure visual separation
  const displayMinIdx = Math.min(minIdx, maxIdx - 1);
  const displayMaxIdx = Math.max(maxIdx, minIdx + 1);

  const idxToPercent = (idx) => (idx / (steps.length - 1)) * 100;
  const formatVal = (val) => val === Infinity ? '∞' : `${val}`;

  const clientXToIdx = useCallback((clientX) => {
    const rect = trackRef.current.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    return Math.round(ratio * (steps.length - 1));
  }, [steps.length]);

  const handleDragStart = useCallback((handle, e) => {
    e.preventDefault();
    dragging.current = handle;
  }, []);

  const handleDragMove = useCallback((e) => {
    if (!dragging.current) return;
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const idx = clientXToIdx(clientX);
    if (dragging.current === 'min') {
      const clampedIdx = Math.min(idx, maxIdx - 1);
      onMinChange(steps[Math.max(0, clampedIdx)]);
    } else {
      const clampedIdx = Math.max(idx, minIdx + 1);
      onMaxChange(steps[Math.min(steps.length - 1, clampedIdx)]);
    }
  }, [clientXToIdx, minIdx, maxIdx, steps, onMinChange, onMaxChange]);

  const handleDragEnd = useCallback(() => {
    dragging.current = null;
  }, []);

  useEffect(() => {
    const move = (e) => handleDragMove(e);
    const end = () => handleDragEnd();
    window.addEventListener('touchmove', move, { passive: false });
    window.addEventListener('touchend', end);
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', end);
    return () => {
      window.removeEventListener('touchmove', move);
      window.removeEventListener('touchend', end);
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', end);
    };
  }, [handleDragMove, handleDragEnd]);

  const handleInputSubmit = () => {
    const val = Number(inputValue);
    if (!isNaN(val) && val >= 0) {
      if (editingField === 'min') {
        onMinChange(Math.min(val, maxVal === Infinity ? config.maxFinite : maxVal));
      } else {
        onMaxChange(val > config.maxFinite ? Infinity : Math.max(val, minVal));
      }
    }
    setEditingField(null);
  };

  const isFiltered = minVal > 0 || maxVal < Infinity;

  return (
    <div>
      {/* Label + clickable value display */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-bold text-gray-400">{config.label}</span>
        <div className="flex items-center gap-1">
          {editingField === 'min' ? (
            <input
              autoFocus
              type="number"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onBlur={handleInputSubmit}
              onKeyDown={(e) => e.key === 'Enter' && handleInputSubmit()}
              className="w-16 min-h-[2.25rem] bg-gray-800 text-routy-primary text-sm text-center py-1.5 rounded-lg border border-routy-primary focus:outline-none font-bold"
              min={0}
            />
          ) : (
            <button
              onClick={() => { setEditingField('min'); setInputValue(minVal === Infinity ? '' : String(minVal)); }}
              className={`min-w-[3rem] min-h-[2.25rem] px-3 py-1.5 rounded-lg text-sm font-bold transition-all ${
                isFiltered
                  ? 'bg-routy-primary/20 text-routy-primary border border-routy-primary/40 active:bg-routy-primary/30'
                  : 'bg-gray-800 text-gray-300 border border-gray-700 active:bg-gray-700'
              }`}
            >
              {formatVal(minVal)}
            </button>
          )}
          <span className="text-gray-500 text-xs">~</span>
          {editingField === 'max' ? (
            <input
              autoFocus
              type="number"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onBlur={handleInputSubmit}
              onKeyDown={(e) => e.key === 'Enter' && handleInputSubmit()}
              className="w-16 min-h-[2.25rem] bg-gray-800 text-routy-primary text-sm text-center py-1.5 rounded-lg border border-routy-primary focus:outline-none font-bold"
              min={0}
            />
          ) : (
            <button
              onClick={() => { setEditingField('max'); setInputValue(maxVal === Infinity ? '' : String(maxVal)); }}
              className={`min-w-[3rem] min-h-[2.25rem] px-3 py-1.5 rounded-lg text-sm font-bold transition-all ${
                isFiltered
                  ? 'bg-routy-primary/20 text-routy-primary border border-routy-primary/40 active:bg-routy-primary/30'
                  : 'bg-gray-800 text-gray-300 border border-gray-700 active:bg-gray-700'
              }`}
            >
              {formatVal(maxVal)}
            </button>
          )}
          <span className={`text-xs font-medium ${isFiltered ? 'text-routy-primary' : 'text-gray-500'}`}>{config.unit}</span>
        </div>
      </div>

      {/* Slider track */}
      <div ref={trackRef} className="relative h-10 flex items-center touch-none">
        <div className="absolute left-0 right-0 h-1 bg-gray-700 rounded-full" />
        <div
          className="absolute h-1 bg-routy-primary rounded-full"
          style={{
            left: `${idxToPercent(displayMinIdx)}%`,
            right: `${100 - idxToPercent(displayMaxIdx)}%`,
          }}
        />
        <div
          className="absolute w-6 h-6 bg-white rounded-full shadow-lg border-2 border-routy-primary cursor-grab active:cursor-grabbing -translate-x-1/2 touch-none z-10"
          style={{ left: `${idxToPercent(displayMinIdx)}%` }}
          onTouchStart={(e) => handleDragStart('min', e)}
          onMouseDown={(e) => handleDragStart('min', e)}
        />
        <div
          className="absolute w-6 h-6 bg-white rounded-full shadow-lg border-2 border-routy-primary cursor-grab active:cursor-grabbing -translate-x-1/2 touch-none z-10"
          style={{ left: `${idxToPercent(displayMaxIdx)}%` }}
          onTouchStart={(e) => handleDragStart('max', e)}
          onMouseDown={(e) => handleDragStart('max', e)}
        />
      </div>
      <div className="relative h-4 text-[10px] text-gray-600 mt-0.5">
        {(() => {
          const lastIdx = steps.length - 1;
          const labelIndices = [0, Math.round(lastIdx * 0.25), Math.round(lastIdx * 0.5), Math.round(lastIdx * 0.75), lastIdx];
          return [...new Set(labelIndices)].map((idx) => (
            <span
              key={idx}
              className={`absolute ${idx === 0 ? '' : idx === lastIdx ? '-translate-x-full' : '-translate-x-1/2'}`}
              style={{ left: `${idxToPercent(idx)}%` }}
            >
              {steps[idx] === Infinity ? '∞' : steps[idx]}
            </span>
          ));
        })()}
      </div>
    </div>
  );
};

const RangeFilterModal = ({ isOpen, onClose, filters, onApply }) => {
  const [dMin, setDMin] = useState(0);
  const [dMax, setDMax] = useState(Infinity);
  const [eMin, setEMin] = useState(0);
  const [eMax, setEMax] = useState(Infinity);

  // Sync from props when opening
  useEffect(() => {
    if (isOpen && filters) {
      setDMin(filters.minDistance ? Number(filters.minDistance) / 1000 : 0);
      setDMax(filters.maxDistance ? Number(filters.maxDistance) / 1000 : Infinity);
      setEMin(filters.minElevation ? Number(filters.minElevation) : 0);
      setEMax(filters.maxElevation ? Number(filters.maxElevation) : Infinity);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const hasFilter = dMin > 0 || dMax < Infinity || eMin > 0 || eMax < Infinity;

  const handleApply = () => {
    onApply({
      minDistance: dMin === 0 ? '' : String(dMin * 1000),
      maxDistance: dMax === Infinity ? '' : String(dMax * 1000),
      minElevation: eMin === 0 ? '' : String(eMin),
      maxElevation: eMax === Infinity ? '' : String(eMax),
    });
    onClose();
  };

  const handleReset = () => {
    setDMin(0);
    setDMax(Infinity);
    setEMin(0);
    setEMax(Infinity);
  };

  return (
    <div className="fixed inset-0 z-[150] flex items-end md:items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div
        className="relative w-full max-w-sm mx-3 mb-3 md:mb-0 bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-white font-bold text-base">필터</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-white p-1">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Distance slider */}
        <div className="mb-6">
          <RangeSlider
            config={CONFIGS.distance}
            minVal={dMin}
            maxVal={dMax}
            onMinChange={setDMin}
            onMaxChange={setDMax}
          />
        </div>

        {/* Elevation slider */}
        <div className="mb-6">
          <RangeSlider
            config={CONFIGS.elevation}
            minVal={eMin}
            maxVal={eMax}
            onMinChange={setEMin}
            onMaxChange={setEMax}
          />
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          {hasFilter && (
            <button
              onClick={handleReset}
              className="px-4 py-2.5 rounded-xl text-sm font-medium text-gray-400 bg-gray-800 border border-gray-700 active:bg-gray-700"
            >
              초기화
            </button>
          )}
          <button
            onClick={handleApply}
            className="flex-1 py-2.5 rounded-xl text-sm font-bold text-white bg-routy-primary active:brightness-90"
          >
            적용
          </button>
        </div>
      </div>
    </div>
  );
};

export default RangeFilterModal;
