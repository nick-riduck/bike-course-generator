console.log("Main script starting...");
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import * as Sentry from '@sentry/react'
import posthog from 'posthog-js'
import './index.css'
import App from './App.jsx'
import { AuthProvider } from './AuthContext'
import { initGA } from './utils/analytics'

// Initialize Sentry
Sentry.init({
  dsn: "https://b5f5cb7d8513b64a47468ac27d9dc6d3@o4511017491169280.ingest.us.sentry.io/4511017591570432",
  enabled: import.meta.env.PROD, // Disable Sentry network requests in development
  integrations: [
    Sentry.browserTracingIntegration(),
    Sentry.replayIntegration(),
  ],
  tracesSampleRate: 1.0,
  replaysSessionSampleRate: 0.1,
  replaysOnErrorSampleRate: 1.0,
});

// Initialize PostHog
posthog.init('phc_stRRL5l68rbqaxolbumgYm2j72tCFKsxWbQkcOxHfuQ', {
  api_host: 'https://us.i.posthog.com',
  person_profiles: 'identified_only',
  capture_pageview: true,
  capture_pageleave: true,
  session_recording: {
    recordCrossOriginIframes: true,
  },
  // In development, we can disable capturing to reduce console errors without breaking the app
  opt_out_capturing_by_default: !import.meta.env.PROD,
});

// Initialize Google Analytics
initGA();

// INP measurement (dev only)
if (!import.meta.env.PROD) {
  import('./utils/measureINP.js').then(({ observeINP }) => observeINP());
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/*" element={<App />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  </StrictMode>,
)
