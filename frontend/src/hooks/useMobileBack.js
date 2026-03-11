import { useEffect, useRef } from 'react';

/**
 * Centralized mobile back-button handler.
 *
 * Accepts an ordered array of "layers" (highest priority first).
 * Each layer: { id: string, isOpen: boolean, onClose: () => void }
 *
 * - When layers open, history entries are pushed so the browser back
 *   button closes them instead of navigating away.
 * - When the user presses back, the topmost open layer is closed.
 * - When layers are closed via UI (X button, etc.), the matching
 *   history entries are silently removed.
 */
export default function useMobileBack(layers) {
  const layersRef = useRef(layers);
  layersRef.current = layers;

  const guardCount = useRef(0);
  const skipPopCount = useRef(0);

  const openCount = layers.filter((l) => l.isOpen).length;

  // Stable popstate listener (mounted once)
  useEffect(() => {
    const handlePopState = () => {
      // If this popstate was triggered by our own history.go() cleanup, skip it
      if (skipPopCount.current > 0) {
        skipPopCount.current--;
        return;
      }

      guardCount.current = Math.max(0, guardCount.current - 1);

      const top = layersRef.current.find((l) => l.isOpen);
      if (top) top.onClose();
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  // Sync history depth with the number of open layers
  useEffect(() => {
    const target = openCount;
    const current = guardCount.current;

    if (target > current) {
      // Layers opened — push history entries
      for (let i = 0; i < target - current; i++) {
        window.history.pushState({ mobileBack: true }, '');
      }
      guardCount.current = target;
    } else if (target < current) {
      // Layers closed via UI (not back button) — remove excess entries
      const excess = current - target;
      skipPopCount.current++; // history.go(-n) fires exactly 1 popstate
      window.history.go(-excess);
      guardCount.current = target;
    }
    // target === current → guards already in sync, nothing to do
  }, [openCount]);
}
