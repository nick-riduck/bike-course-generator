import React, { useMemo, useRef } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Filler,
  Legend,
} from 'chart.js';
import { Line } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Filler,
  Legend
);

const getDistanceFromLatLonInKm = (lat1, lon1, lat2, lon2) => {
  const R = 6371; 
  const dLat = (lat2 - lat1) * (Math.PI / 180);
  const dLon = (lon2 - lon1) * (Math.PI / 180);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(lat1 * (Math.PI / 180)) * Math.cos(lat2 * (Math.PI / 180)) *
    Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
};

const ElevationChart = ({ segments, onHoverPoint }) => {
  const chartRef = useRef(null);
  const lastHoverIndex = useRef(-1);

  // Calculate Checkpoint Distances
  const checkpointDistances = useMemo(() => {
    if (!segments || segments.length === 0) return [];
    
    let totalDist = 0;
    const cpDists = [0]; // Start point is always at 0

    segments.forEach(segment => {
       if (!segment.geometry?.coordinates) return;
       // Calculate length of this segment to add to total
       let segLen = 0;
       const coords = segment.geometry.coordinates;
       for(let i=0; i<coords.length-1; i++) {
           const p1 = coords[i];
           const p2 = coords[i+1];
           segLen += getDistanceFromLatLonInKm(p1[1], p1[0], p2[1], p2[0]);
       }
       totalDist += segLen;
       cpDists.push(totalDist); // End of this segment (which is Start of next CP)
    });
    
    // Remove the last point if it's just the finish line, or keep it if desired. 
    // Usually markers are between segments. 
    return cpDists;
  }, [segments]);

  const flatData = useMemo(() => {
    if (!segments || segments.length === 0) return [];

    let totalDist = 0;
    const rawPoints = [];

    segments.forEach(segment => {
        if (!segment.geometry?.coordinates) return;
        const coords = segment.geometry.coordinates;
        
        coords.forEach((coord) => {
            const lng = parseFloat(coord[0]);
            const lat = parseFloat(coord[1]);
            const ele = coord[2] !== undefined ? parseFloat(coord[2]) : 0;
            
            if (rawPoints.length > 0) {
                const prev = rawPoints[rawPoints.length - 1];
                if (prev.lng === lng && prev.lat === lat) return;
                totalDist += getDistanceFromLatLonInKm(prev.lat, prev.lng, lat, lng);
            }

            rawPoints.push({
                dist_km: totalDist, 
                ele: ele, 
                lng,
                lat
            });
        });
    });

    if (rawPoints.length < 50 && totalDist > 0) {
        const interpolated = [];
        for (let i = 0; i < rawPoints.length - 1; i++) {
            const p1 = rawPoints[i];
            const p2 = rawPoints[i+1];
            const segDist = p2.dist_km - p1.dist_km;
            const steps = Math.max(10, Math.ceil(segDist * 20));

            for (let j = 0; j < steps; j++) {
                const t = j / steps;
                interpolated.push({
                    dist_km: p1.dist_km + (p2.dist_km - p1.dist_km) * t,
                    ele: p1.ele + (p2.ele - p1.ele) * t,
                    lng: p1.lng + (p2.lng - p1.lng) * t,
                    lat: p1.lat + (p2.lat - p1.lat) * t
                });
            }
        }
        interpolated.push(rawPoints[rawPoints.length - 1]);
        return interpolated;
    }

    return rawPoints;
  }, [segments]);

  const chartData = useMemo(() => {
    const labels = flatData.map(p => p.dist_km.toFixed(2));
    const elevations = flatData.map(p => p.ele);

    return {
      labels,
      datasets: [
        {
          fill: true,
          label: 'Elevation',
          data: elevations,
          borderColor: '#2a9e92',
          backgroundColor: 'rgba(42, 158, 146, 0.2)',
          tension: 0.4,
          pointRadius: 0, 
          pointHoverRadius: 5,
          borderWidth: 2,
        },
      ],
    };
  }, [flatData]);

  // Custom Plugin to draw vertical lines at checkpoints
  const cpLinePlugin = {
    id: 'cpLines',
    afterDatasetsDraw(chart) {
        const { ctx, chartArea: { top, bottom }, scales: { x } } = chart;
        
        ctx.save();
        ctx.beginPath();
        ctx.lineWidth = 1;
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)'; // Weak white line
        ctx.setLineDash([5, 5]); // Dashed line

        checkpointDistances.forEach((cpDist, index) => {
            // Find the closest x-axis index for this distance
            // Since labels are strings "0.00", "0.01", we need to match appropriately
            // or rely on the fact that flatData corresponds to labels 1:1
            
            // Find closest data point index
            const closestIdx = flatData.findIndex(p => p.dist_km >= cpDist);
            
            if (closestIdx !== -1) {
                const xPos = x.getPixelForValue(closestIdx);
                
                // Draw Line
                ctx.moveTo(xPos, top);
                ctx.lineTo(xPos, bottom);
                
                // Draw CP Label
                ctx.fillStyle = index === 0 ? '#4CAF50' : (index === checkpointDistances.length - 1 ? '#F44336' : '#2a9e92');
                ctx.font = '10px sans-serif';
                ctx.textAlign = 'center';
                ctx.fillText(index + 1, xPos, top + 10);
            }
        });

        ctx.stroke();
        ctx.restore();
    }
  };

  const handleClearHover = () => {
    lastHoverIndex.current = -1;
    if (onHoverPoint) onHoverPoint(null);
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        mode: 'index',
        intersect: false,
        backgroundColor: '#1E1E1E',
        titleColor: '#fff',
        bodyColor: '#2a9e92',
        borderColor: '#444',
        borderWidth: 1,
        callbacks: {
          label: (context) => `Ele: ${Math.round(context.parsed.y)}m`,
          title: (items) => `Dist: ${items[0].label}km`,
        }
      },
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: { color: '#666', maxRotation: 0, autoSkip: true, maxTicksLimit: 10 },
      },
      y: {
        grid: { color: '#333' },
        ticks: { color: '#666' },
        beginAtZero: false,
      },
    },
    interaction: {
      mode: 'nearest',
      axis: 'x',
      intersect: false,
    },
    onHover: (event, activeElements) => {
      if (activeElements.length > 0) {
        const index = activeElements[0].index;
        
        if (index !== lastHoverIndex.current) {
            lastHoverIndex.current = index;
            const point = flatData[index];
            if (point && onHoverPoint) {
                onHoverPoint({ lng: point.lng, lat: point.lat });
            }
        }
      } else {
        if (lastHoverIndex.current !== -1) {
            handleClearHover();
        }
      }
    },
  };

  if (!segments || segments.length === 0) {
    return (
      <div className="w-full h-48 bg-[#1E1E1E] rounded-xl border border-gray-800 flex items-center justify-center text-gray-500 italic mt-6">
        No elevation data available
      </div>
    );
  }

  return (
    <div 
        className="w-full bg-[#1E1E1E]/90 backdrop-blur-md rounded-xl border border-gray-800 p-4 mt-6 shadow-lg h-[250px]"
        onMouseLeave={handleClearHover}
    >
      <h3 className="text-xs font-bold text-[#2a9e92] mb-2 uppercase tracking-wider flex items-center gap-2">
        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
        </svg>
        Elevation Profile
      </h3>
      <div className="w-full h-[190px]">
        {/* Pass custom plugin via plugins prop */}
        <Line ref={chartRef} data={chartData} options={options} plugins={[cpLinePlugin]} />
      </div>
    </div>
  );
};

export default ElevationChart;