import React, { useEffect, useMemo, useRef } from 'react';
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

const getGradeColor = (grade, alpha = 1) => {
  if (grade < -0.05) return `rgba(30, 136, 229, ${alpha})`;   // 급 내리막 (파랑)
  if (grade < -0.01) return `rgba(79, 195, 247, ${alpha})`;   // 완만 내리막 (하늘)
  if (grade <= 0.01) return `rgba(102, 187, 106, ${alpha})`;  // 평지 (초록)
  if (grade <= 0.05) return `rgba(255, 167, 38, ${alpha})`;   // 완만 오르막 (주황)
  if (grade <= 0.10) return `rgba(239, 83, 80, ${alpha})`;    // 가파른 오르막 (빨강)
  return `rgba(173, 20, 87, ${alpha})`;                        // 급경사 (보라)
};

const calcGrade = (ctx) => {
  const p0 = ctx.p0.parsed;
  const p1 = ctx.p1.parsed;
  const distDiff = p1.x - p0.x;
  if (distDiff === 0) return 0;
  return (p1.y - p0.y) / (distDiff * 1000); // km → m 변환
};

const ElevationChart = ({ segments, checkpoints = [], onHoverPoint, onSelectPoint, mapHoverCoord }) => {
  const chartRef = useRef(null);
  const lastHoverIndex = useRef(-1);
  const checkpointDistancesRef = useRef([]);
  const mapHoverChartPointRef = useRef(null);

  const flatData = useMemo(() => {
    if (!segments || segments.length === 0) return [];

    let totalDist = 0;
    const rawPoints = [];

    segments.forEach((segment) => {
      const coords = segment.geometry?.coordinates;
      if (!Array.isArray(coords) || coords.length === 0) {
        return;
      }

      coords.forEach((coord) => {
        const lng = parseFloat(coord[0]);
        const lat = parseFloat(coord[1]);
        const rawEle = coord[2] !== undefined && coord[2] !== null ? parseFloat(coord[2]) : NaN;
        const prevEle = rawPoints.length > 0 ? rawPoints[rawPoints.length - 1].ele : 0;
        const ele = Number.isFinite(rawEle) ? rawEle : prevEle;

        if (!Number.isFinite(lng) || !Number.isFinite(lat)) return;

        if (rawPoints.length > 0) {
          const prev = rawPoints[rawPoints.length - 1];
          if (prev.lng === lng && prev.lat === lat) return;
          totalDist += getDistanceFromLatLonInKm(prev.lat, prev.lng, lat, lng);
        }

        rawPoints.push({
          dist_km: totalDist,
          ele,
          lng,
          lat
        });
      });
    });

    let finalPoints = rawPoints;
    if (rawPoints.length < 50 && totalDist > 0) {
      const interpolated = [];
      for (let i = 0; i < rawPoints.length - 1; i++) {
        const p1 = rawPoints[i];
        const p2 = rawPoints[i + 1];
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
      finalPoints = interpolated;
    }

    return finalPoints;
  }, [segments]);

  const checkpointDistances = useMemo(() => {
    if (!Array.isArray(checkpoints) || checkpoints.length === 0) return [];
    return checkpoints
      .filter(cp => Number.isFinite(cp.dist_km))
      .map(cp => cp.dist_km);
  }, [checkpoints]);

  const chartData = useMemo(() => {
    return {
      datasets: [
        {
          fill: true,
          label: 'Elevation',
          data: flatData.map(p => ({ x: p.dist_km, y: p.ele })),
          borderColor: '#2a9e92',
          backgroundColor: 'rgba(42, 158, 146, 0.2)',
          segment: {
            borderColor: (ctx) => getGradeColor(calcGrade(ctx)),
            backgroundColor: (ctx) => getGradeColor(calcGrade(ctx), 0.3),
          },
          tension: 0.3,
          pointRadius: 0,
          pointHoverRadius: 5,
          borderWidth: 2,
        },
      ],
    };
  }, [flatData]);

  const mapHoverChartPoint = useMemo(() => {
    if (!mapHoverCoord || !Number.isFinite(mapHoverCoord.lng) || !Number.isFinite(mapHoverCoord.lat)) return null;
    if (!flatData || flatData.length === 0) return null;

    let nearestPoint = flatData[0];
    let nearestDist = getDistanceFromLatLonInKm(
      mapHoverCoord.lat, mapHoverCoord.lng,
      nearestPoint.lat, nearestPoint.lng
    );

    for (let i = 1; i < flatData.length; i++) {
      const point = flatData[i];
      const dist = getDistanceFromLatLonInKm(mapHoverCoord.lat, mapHoverCoord.lng, point.lat, point.lng);
      if (dist < nearestDist) {
        nearestPoint = point;
        nearestDist = dist;
      }
    }

    return nearestPoint;
  }, [mapHoverCoord, flatData]);

  // Refs: always hold latest values so stable plugin instances can read them
  checkpointDistancesRef.current = checkpointDistances;
  mapHoverChartPointRef.current = mapHoverChartPoint;

  // Stable plugin instances (created once, read from refs)
  const plugins = useRef([
    {
      id: 'cpLines',
      afterDatasetsDraw(chart) {
        const distances = checkpointDistancesRef.current;
        if (!distances || distances.length === 0) return;
        const { ctx, chartArea: { top, bottom, left, right }, scales: { x } } = chart;

        ctx.save();
        ctx.lineWidth = 1;
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'center';

        distances.forEach((cpDist, index) => {
          const xPos = x.getPixelForValue(cpDist);
          if (!Number.isFinite(xPos) || xPos < left) return;
          const clampedX = Math.min(xPos, right);
          const color = index === 0 ? '#4CAF50' : (index === distances.length - 1 ? '#F44336' : '#2a9e92');

          // 각 마커를 독립 path로 그려야 대시 패턴이 항상 처음부터 시작됨
          ctx.beginPath();
          ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
          ctx.setLineDash([5, 5]);
          ctx.moveTo(clampedX, top);
          ctx.lineTo(clampedX, bottom);
          ctx.stroke();

          ctx.fillStyle = color;
          ctx.setLineDash([]);
          ctx.fillText(index + 1, clampedX, top + 10);
        });

        ctx.restore();
      }
    },
    {
      id: 'mapHoverGuide',
      afterDatasetsDraw(chart) {
        const point = mapHoverChartPointRef.current;
        if (!point) return;

        const { ctx, chartArea: { top, bottom, left, right }, scales: { x, y } } = chart;
        const xPos = x.getPixelForValue(point.dist_km);
        if (!Number.isFinite(xPos) || xPos < left || xPos > right) return;

        const yPos = y.getPixelForValue(point.ele);

        ctx.save();
        ctx.beginPath();
        ctx.lineWidth = 1.25;
        ctx.strokeStyle = 'rgba(45, 212, 191, 0.9)';
        ctx.setLineDash([3, 3]);
        ctx.moveTo(xPos, top);
        ctx.lineTo(xPos, bottom);
        ctx.stroke();

        if (Number.isFinite(yPos) && yPos >= top && yPos <= bottom) {
          ctx.setLineDash([]);
          ctx.beginPath();
          ctx.fillStyle = '#2DD4BF';
          ctx.strokeStyle = '#FFFFFF';
          ctx.lineWidth = 1.5;
          ctx.arc(xPos, yPos, 3.8, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
        }

        ctx.restore();
      }
    }
  ]).current;

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || typeof chart.update !== 'function') return;
    chart.update('none');
  }, [mapHoverChartPoint, checkpointDistances]);

  const handleClearHover = () => {
    lastHoverIndex.current = -1;
    if (onHoverPoint) onHoverPoint(null);
  };

  const handleSelectPoint = (point) => {
    if (!point || !onSelectPoint) return;
    onSelectPoint({
      lng: point.lng,
      lat: point.lat,
      dist_km: point.dist_km,
      ele: point.ele
    });
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    layout: {
      padding: {
        top: 10,
        bottom: 0, // 하단 패딩 제거 (부모 컨테이너 패딩 활용)
        left: 0,
        right: 10 // 마지막 라벨 잘림 방지
      }
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        mode: 'index',
        intersect: false,
        backgroundColor: '#111827', // gray-900
        titleColor: '#F3F4F6', // gray-100
        bodyColor: '#2DD4BF', // teal-400
        borderColor: '#374151', // gray-700
        borderWidth: 1,
        padding: 10,
        callbacks: {
          label: (context) => ` Ele: ${Math.round(context.parsed.y)}m`,
          title: (items) => `Dist: ${items[0].parsed.x.toFixed(2)}km`,
        }
      },
    },
    scales: {
      x: {
        type: 'linear',
        min: 0,
        max: flatData.length > 0 ? flatData[flatData.length - 1].dist_km : 10,
        grid: { display: false, drawBorder: false },
        ticks: { 
            color: '#9CA3AF',
            maxRotation: 0, 
            autoSkip: true, 
            maxTicksLimit: 10,
            padding: 4,
            includeBounds: true,
            align: 'inner',
            callback: function(value, index, ticks) {
                // Last Tick: Always show with decimals
                if (index === ticks.length - 1) return `${parseFloat(value.toFixed(2))}km`;
                
                // Other Ticks: Only show if it's an integer
                // Using a small epsilon to handle floating point precision
                if (Math.abs(value - Math.round(value)) < 0.01) {
                    return `${Math.round(value)}km`;
                }
                return '';
            }
        },
        afterBuildTicks: (axis) => {
            const ticks = axis.ticks;
            // Force include the exact max value as the last tick
            if (ticks.length > 0 && ticks[ticks.length - 1].value !== axis.max) {
                ticks.push({ value: axis.max });
            }
        },
        border: { display: false }
      },
      y: {
        grid: { color: '#374151' },
        ticks: { 
            color: '#9CA3AF',
            callback: (value) => `${Math.round(value)}m`,
            padding: 4
        },
        beginAtZero: false,
        border: { display: false }
      },
    },
    interaction: {
      mode: 'nearest',
      axis: 'x',
      intersect: false,
    },
    onClick: (event, activeElements, chart) => {
      if (!onSelectPoint || flatData.length === 0) return;

      let selectedPoint = null;

      if (activeElements.length > 0) {
        selectedPoint = flatData[activeElements[0].index];
      } else {
        const clickedX = event?.x;
        const xScale = chart?.scales?.x;

        if (Number.isFinite(clickedX) && xScale && typeof xScale.getValueForPixel === 'function') {
          const clickedDistKm = xScale.getValueForPixel(clickedX);

          if (Number.isFinite(clickedDistKm)) {
            let nearestPoint = flatData[0];
            let nearestDiff = Math.abs(flatData[0].dist_km - clickedDistKm);

            for (let i = 1; i < flatData.length; i++) {
              const diff = Math.abs(flatData[i].dist_km - clickedDistKm);
              if (diff < nearestDiff) {
                nearestPoint = flatData[i];
                nearestDiff = diff;
              }
            }

            selectedPoint = nearestPoint;
          }
        }
      }

      if (selectedPoint) {
        handleSelectPoint(selectedPoint);
      }
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
      <div className="w-full h-full flex items-center justify-center text-gray-600 text-xs italic tracking-wider">
        Create a route to see elevation profile
      </div>
    );
  }

  return (
    <div 
        className="w-full h-full bg-transparent flex flex-col"
        onMouseLeave={handleClearHover}
    >
      <div className="flex-1 w-full min-h-0 relative">
        <Line ref={chartRef} data={chartData} options={options} plugins={plugins} />
      </div>
    </div>
  );
};

export default ElevationChart;
