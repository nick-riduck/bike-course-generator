/**
 * Lightweight INP (Interaction to Next Paint) measurement utility.
 * Logs interaction durations to console and optionally to a callback.
 *
 * Usage: import and call once in main.jsx:
 *   import { observeINP } from './utils/measureINP';
 *   observeINP((entry) => console.table(entry));
 */
export function observeINP(onEntry) {
  if (typeof PerformanceObserver === 'undefined') return;

  try {
    const po = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        // event timing entries
        const dur = entry.duration; // processing + presentation delay
        const target = entry.target?.tagName
          ? `${entry.target.tagName.toLowerCase()}.${[...entry.target.classList].slice(0, 3).join('.')}`
          : '<unknown>';

        const data = {
          name: entry.name,
          duration: Math.round(dur),
          processingStart: Math.round(entry.processingStart - entry.startTime),
          processingEnd: Math.round(entry.processingEnd - entry.startTime),
          inputDelay: Math.round(entry.processingStart - entry.startTime),
          processingTime: Math.round(entry.processingEnd - entry.processingStart),
          presentationDelay: Math.round(entry.startTime + dur - entry.processingEnd),
          target,
        };

        if (dur > 50) {
          console.warn(`[INP] ${data.name} on ${target}: ${data.duration}ms (input:${data.inputDelay} proc:${data.processingTime} paint:${data.presentationDelay})`, data);
        }

        if (onEntry) onEntry(data);
      }
    });

    po.observe({ type: 'event', buffered: true, durationThreshold: 16 });
    return po;
  } catch {
    // PerformanceObserver event timing not supported
    return null;
  }
}
