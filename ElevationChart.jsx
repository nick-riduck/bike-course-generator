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
import useCourseStore from '../stores/useCourseStore';

// Register Chart.js components
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

const ElevationChart = () => {
  const { gpxData, hoveredDist, setHoveredDist } = useCourseStore();
  const chartRef = useRef(null);

  // Prepare Chart.js data structure
  const data = useMemo(() => {
    if (!gpxData || gpxData.length === 0) return { labels: [], datasets: [] };
    
    // Downsample for performance if needed, but Chart.js handles thousands well
    const labels = gpxData.map(p => (p.dist_m / 1000).toFixed(2));
    const elevations = gpxData.map(p => p.ele);
    
    return {
      labels,
      datasets: [
        {
          fill: true,
          label: 'Elevation (m)',
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
  }, [gpxData]);

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false, // Disable animation for performance
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
          label: (context) => `Ele: ${context.parsed.y}m`,
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
        const dist = gpxData[index].dist_m;
        
        // Prevent infinite loop: Only update if value changed
        if (dist !== hoveredDist) {
          setHoveredDist(dist);
        }
      } else {
        if (hoveredDist !== null) {
          setHoveredDist(null);
        }
      }
    },
  };

  if (!gpxData || gpxData.length === 0) {
    return (
      <div className="w-full h-48 bg-[#1E1E1E] rounded-xl border border-gray-800 flex items-center justify-center text-gray-500 italic mt-6">
        Load a GPX file to see elevation profile
      </div>
    );
  }

  return (
    <div className="w-full bg-[#1E1E1E] rounded-xl border border-gray-800 p-4 mt-6 shadow-lg h-[300px]">
      <h3 className="text-sm font-bold text-[#2a9e92] mb-2 uppercase tracking-wider">Elevation Profile</h3>
      <div className="w-full h-[230px]">
        <Line ref={chartRef} data={data} options={options} />
      </div>
    </div>
  );
};

export default ElevationChart;
