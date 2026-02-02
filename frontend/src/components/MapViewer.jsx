import React, { useState } from 'react';
import DeckGL from '@deck.gl/react';
import { PolygonLayer } from '@deck.gl/layers';
import { Map } from 'react-map-gl/maplibre';
import { LightingEffect, AmbientLight, _SunLight as SunLight } from '@deck.gl/core';
import 'maplibre-gl/dist/maplibre-gl.css';

const INITIAL_VIEW_STATE = {
  longitude: 126.99,
  latitude: 37.55,
  zoom: 13,
  pitch: 60,
  bearing: 30
};

const DUMMY_COURSE = [
  { start: [126.990, 37.550, 100], end: [126.992, 37.552, 120], color: [244, 67, 54] },
  { start: [126.992, 37.552, 120], end: [126.995, 37.555, 120], color: [165, 214, 167] },
  { start: [126.995, 37.555, 120], end: [127.000, 37.560, 90], color: [0, 172, 193] },
];

// Create a lighting effect for the scene
const ambientLight = new AmbientLight({
  color: [255, 255, 255],
  intensity: 1.0
});

const sunLight = new SunLight({
  timestamp: Date.UTC(2024, 5, 15, 14), // Noonish
  color: [255, 255, 255],
  intensity: 1.0,
  _shadow: true
});

const lightingEffect = new LightingEffect({ ambientLight, sunLight });

const material = {
  ambient: 0.8,
  diffuse: 0.6,
  shininess: 32,
  specularColor: [60, 64, 70]
};

const MapViewer = () => {
  const Z_SCALE = 5.0;

  const triangleData = DUMMY_COURSE.flatMap(d => {
    const s = d.start;
    const e = d.end;
    const bl = [s[0], s[1], 0];
    const br = [e[0], e[1], 0];
    const tr = [e[0], e[1], e[2] * Z_SCALE];
    const tl = [s[0], s[1], s[2] * Z_SCALE];

    return [
      { polygon: [bl, br, tr], color: d.color },
      { polygon: [bl, tr, tl], color: d.color }
    ];
  });

  const layers = [
    new PolygonLayer({
      id: 'curtain-wall',
      data: triangleData,
      pickable: true,
      stroked: false,
      filled: true,
      extruded: false,
      wireframe: false,
      parameters: { cull: false, depthTest: true },
      getPolygon: d => d.polygon,
      getFillColor: d => d.color,
      material,
    })
  ];

  return (
    <div className="relative w-full h-[600px] rounded-xl overflow-hidden border border-gray-700 shadow-2xl">
      <Map
        initialViewState={INITIAL_VIEW_STATE}
        style={{width: '100%', height: '100%'}}
        mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
        onMove={evt => setViewState(evt.viewState)}
      >
        <DeckGL
          viewState={viewState}
          controller={true}
          layers={layers}
          // effects={[lightingEffect]}
          getTooltip={({object}) => object && `Segment`}
          style={{background: 'transparent'}} // Ensure DeckGL is transparent overlay
        />
      </Map>
      
      {/* Overlay UI }
    </div>
  );
};

export default MapViewer;