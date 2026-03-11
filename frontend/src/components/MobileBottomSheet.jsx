import React, { useState, useRef, useCallback, useEffect } from 'react';

// Snap points as percentage of viewport height (from bottom)
const SNAP_POINTS = {
  collapsed: 5, // ~5vh — slim bar with title
  peek: 45,     // ~45vh — half screen
  full: 99,     // ~99% of parent — near full screen
};

const getSnapName = (height) => {
  const mid1 = (SNAP_POINTS.collapsed + SNAP_POINTS.peek) / 2;
  const mid2 = (SNAP_POINTS.peek + SNAP_POINTS.full) / 2;
  if (height <= mid1) return 'collapsed';
  if (height <= mid2) return 'peek';
  return 'full';
};

const MobileBottomSheet = ({ isOpen, onClose, children, stickyHeader, title, icon, initialSnap = 'peek', onSnapChange, requestSnap }) => {
  const [sheetHeight, setSheetHeight] = useState(isOpen ? SNAP_POINTS[initialSnap] : 0);
  const [isDragging, setIsDragging] = useState(false);
  const dragStartY = useRef(0);
  const dragStartHeight = useRef(0);
  const sheetRef = useRef(null);
  const didDrag = useRef(false);
  const lastSnap = useRef(null);

  const isCollapsed = sheetHeight <= SNAP_POINTS.collapsed + 2;

  // Report snap state changes
  useEffect(() => {
    if (!isDragging && onSnapChange) {
      const snap = getSnapName(sheetHeight);
      if (snap !== lastSnap.current) {
        lastSnap.current = snap;
        onSnapChange(snap);
      }
    }
  }, [sheetHeight, isDragging, onSnapChange]);

  // Open/close animation
  useEffect(() => {
    if (isOpen) {
      setSheetHeight(SNAP_POINTS[initialSnap]);
    } else {
      setSheetHeight(0);
    }
  }, [isOpen, initialSnap]);

  // External snap control
  useEffect(() => {
    if (requestSnap && SNAP_POINTS[requestSnap] !== undefined) {
      setSheetHeight(SNAP_POINTS[requestSnap]);
    }
  }, [requestSnap]);

  const snapToNearest = useCallback((currentHeight) => {
    const points = [SNAP_POINTS.collapsed, SNAP_POINTS.peek, SNAP_POINTS.full];
    let closest = points[0];
    let minDist = Math.abs(currentHeight - points[0]);
    for (const p of points) {
      const dist = Math.abs(currentHeight - p);
      if (dist < minDist) {
        minDist = dist;
        closest = p;
      }
    }
    setSheetHeight(closest);
  }, []);

  const handleDragStart = useCallback((e) => {
    setIsDragging(true);
    didDrag.current = false;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    dragStartY.current = clientY;
    dragStartHeight.current = sheetHeight;
  }, [sheetHeight]);

  const handleDragMove = useCallback((e) => {
    if (!isDragging) return;
    e.preventDefault(); // prevent pull-to-refresh
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    const deltaY = dragStartY.current - clientY;
    if (Math.abs(deltaY) > 3) didDrag.current = true;
    const parentHeight = sheetRef.current?.parentElement?.offsetHeight || window.innerHeight;
    const deltaVh = (deltaY / parentHeight) * 100;
    const newHeight = Math.max(SNAP_POINTS.collapsed, Math.min(SNAP_POINTS.full, dragStartHeight.current + deltaVh));
    setSheetHeight(newHeight);
  }, [isDragging]);

  const handleDragEnd = useCallback(() => {
    if (!isDragging) return;
    setIsDragging(false);
    snapToNearest(sheetHeight);
  }, [isDragging, sheetHeight, snapToNearest]);

  // Tap (no drag) on collapsed bar → expand to peek
  const handleTap = useCallback(() => {
    if (!didDrag.current && isCollapsed) {
      setSheetHeight(SNAP_POINTS.peek);
    }
  }, [isCollapsed]);

  // Global listeners for drag
  useEffect(() => {
    if (isDragging) {
      const moveHandler = (e) => handleDragMove(e);
      const endHandler = () => handleDragEnd();
      window.addEventListener('touchmove', moveHandler, { passive: false });
      window.addEventListener('touchend', endHandler);
      window.addEventListener('mousemove', moveHandler);
      window.addEventListener('mouseup', endHandler);
      return () => {
        window.removeEventListener('touchmove', moveHandler);
        window.removeEventListener('touchend', endHandler);
        window.removeEventListener('mousemove', moveHandler);
        window.removeEventListener('mouseup', endHandler);
      };
    }
  }, [isDragging, handleDragMove, handleDragEnd]);

  // Shared drag props for handle + stickyHeader
  const dragProps = {
    onTouchStart: handleDragStart,
    onMouseDown: handleDragStart,
  };

  if (!isOpen) return null;

  return (
    <div
      ref={sheetRef}
      className="md:hidden absolute inset-x-0 z-40 pointer-events-auto flex flex-col"
      style={{
        height: `${sheetHeight}%`,
        bottom: 0,
        transition: isDragging ? 'none' : 'height 0.3s ease-out',
      }}
    >
      <div className="flex-1 flex flex-col bg-gray-900/97 backdrop-blur-xl border-t border-gray-700/60 rounded-t-2xl shadow-2xl overflow-hidden min-h-0">
        {/* Handle area — always visible & draggable */}
        <div
          className="shrink-0 touch-none cursor-grab active:cursor-grabbing"
          {...dragProps}
          onClick={handleTap}
        >
          <div className="flex flex-col items-center pt-2.5 pb-2 px-4 gap-1.5">
            <div className="w-10 h-1 bg-gray-600 rounded-full" />
            {isCollapsed && (
              <div className="flex items-center gap-1.5">
                {icon && <span className="text-sm">{icon}</span>}
                <span className="text-xs font-bold text-gray-300">{title}</span>
                <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 15l7-7 7 7" />
                </svg>
              </div>
            )}
          </div>
        </div>

        {/* Sticky header — draggable, same as handle */}
        {!isCollapsed && stickyHeader && (
          <div
            className="shrink-0 touch-none cursor-grab active:cursor-grabbing"
            {...dragProps}
          >
            {stickyHeader}
          </div>
        )}

        {/* Scrollable content — hidden when collapsed */}
        {!isCollapsed && (
          <div className="flex-1 overflow-hidden min-h-0 flex flex-col">
            {children}
          </div>
        )}
      </div>
    </div>
  );
};

export default MobileBottomSheet;
