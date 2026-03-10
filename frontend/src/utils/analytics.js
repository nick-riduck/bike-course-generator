// GA4 Analytics utility
const GA_MEASUREMENT_ID = 'G-FZ2GBDKLFE';

// Initialize gtag
export const initGA = () => {
  // Load gtag script
  const script = document.createElement('script');
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${GA_MEASUREMENT_ID}`;
  document.head.appendChild(script);

  window.dataLayer = window.dataLayer || [];
  window.gtag = function () {
    window.dataLayer.push(arguments);
  };
  window.gtag('js', new Date());
  window.gtag('config', GA_MEASUREMENT_ID);
};

// Page view (call on route change)
export const trackPageView = (path, title) => {
  if (!window.gtag) return;
  window.gtag('event', 'page_view', {
    page_path: path,
    page_title: title,
  });
};

// Custom events
export const trackEvent = (eventName, params = {}) => {
  if (!window.gtag) return;
  window.gtag('event', eventName, params);
};

// Set user ID for cross-device tracking
export const setUserId = (userId) => {
  if (!window.gtag) return;
  window.gtag('config', GA_MEASUREMENT_ID, { user_id: userId });
};

// Pre-defined event helpers
export const analytics = {
  // Auth
  login: (method = 'google') =>
    trackEvent('login', { method }),
  signup: (method = 'google') =>
    trackEvent('sign_up', { method }),

  // Route
  routeSearch: (query, resultsCount, filters = {}) =>
    trackEvent('route_search', { search_term: query, results_count: resultsCount, ...filters }),
  routeViewed: (routeId, distance, source = 'search') =>
    trackEvent('route_viewed', { route_id: routeId, distance, source }),
  routeCreated: (routeId, distance, elevation, tagCount) =>
    trackEvent('route_created', { route_id: routeId, distance, elevation_gain: elevation, tag_count: tagCount }),
  routeExported: (format) =>
    trackEvent('route_exported', { format }),

  // Waypoint
  waypointViewed: (waypointId, type) =>
    trackEvent('waypoint_viewed', { waypoint_id: waypointId, waypoint_type: type }),

  // Search tab
  searchTabChanged: (tab) =>
    trackEvent('search_tab_changed', { tab }),
};
