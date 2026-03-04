import {
  ArrowUp, CornerUpLeft, CornerUpRight,
  Utensils, Droplets, Mountain, AlertTriangle, Info, MapPin, Flag, RotateCcw
} from 'lucide-react';

// 내부 타입 상수
export const POINT_TYPES = {
  SECTION_START: 'section_start',
  VIA:           'via',
  TURN_LEFT:     'turn_left',
  TURN_RIGHT:    'turn_right',
  STRAIGHT:      'straight',
  U_TURN:        'u_turn',
  FOOD:          'food',
  WATER:         'water',
  SUMMIT:        'summit',
  DANGER:        'danger',
  INFO:          'info',
};

// 타입별 설정 (아이콘, 라벨, 색상)
export const POINT_TYPE_CONFIG = {
  section_start: { icon: Flag,           label: '구간 시작', color: null },
  turn_left:     { icon: CornerUpLeft,   label: '좌회전',   color: '#3B82F6' },
  turn_right:    { icon: CornerUpRight,  label: '우회전',   color: '#3B82F6' },
  straight:      { icon: ArrowUp,        label: '직진',     color: '#6B7280' },
  u_turn:        { icon: RotateCcw,      label: 'U턴',      color: '#F59E0B' },
  food:          { icon: Utensils,       label: '보급지',   color: '#F97316' },
  water:         { icon: Droplets,       label: '급수',     color: '#06B6D4' },
  summit:        { icon: Mountain,       label: '정상',     color: '#8B5CF6' },
  danger:        { icon: AlertTriangle,  label: '위험',     color: '#EF4444' },
  info:          { icon: Info,           label: '안내',     color: '#6B7280' },
  via:           { icon: MapPin,         label: '경유지',   color: null },
};

// 사용자가 수동 선택 가능한 타입 목록 (section_start 제외)
export const SELECTABLE_TYPES = Object.entries(POINT_TYPE_CONFIG)
  .filter(([k]) => k !== 'section_start')
  .map(([key, cfg]) => ({ key, ...cfg }));

// 3단계 크기 결정
export function getPointTier(point, isFirst, isLast) {
  if (isFirst || isLast) return 'large';
  const specialTypes = ['turn_left','turn_right','straight','u_turn','food','water','summit','danger','info'];
  if (specialTypes.includes(point.type)) return 'large';
  if (point.name) return 'medium';
  return 'small';
}

// 크기별 CSS 클래스
export const TIER_STYLES = {
  large:  { map: 'w-7 h-7 text-[10px]', sidebar: 'w-6 h-6 text-[9px]' },
  medium: { map: 'w-6 h-6 text-[9px]',  sidebar: 'w-5 h-5 text-[8px]' },
  small:  { map: 'w-4 h-4 text-[7px]',  sidebar: 'w-4 h-4 text-[7px]' },
};
