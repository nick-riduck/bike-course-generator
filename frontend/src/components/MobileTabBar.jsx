import React from 'react';

const MobileTabBar = ({ activeTab, onTabChange }) => {
  const tabs = [
    {
      id: 'explore',
      label: '탐색',
      icon: (active) => (
        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={active ? 2.5 : 2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      ),
    },
    {
      id: 'create',
      label: '만들기',
      icon: (active) => (
        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={active ? 2.5 : 2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
        </svg>
      ),
      accent: true,
    },
    {
      id: 'profile',
      label: '내 정보',
      icon: (active) => (
        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill={active ? 'currentColor' : 'none'} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={active ? 0 : 2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
        </svg>
      ),
    },
  ];

  return (
    <nav className="md:hidden flex items-center justify-around bg-gray-900/95 backdrop-blur-md border-t border-gray-800 shrink-0 pb-[env(safe-area-inset-bottom)]">
      {tabs.map((tab) => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={`flex flex-col items-center justify-center gap-0.5 py-2 px-6 min-h-[52px] transition-colors ${
              isActive
                ? tab.accent
                  ? 'text-routy-primary'
                  : 'text-white'
                : 'text-gray-500'
            }`}
          >
            {tab.icon(isActive)}
            <span className={`text-[10px] font-bold ${isActive ? '' : 'font-medium'}`}>
              {tab.label}
            </span>
          </button>
        );
      })}
    </nav>
  );
};

export default MobileTabBar;
