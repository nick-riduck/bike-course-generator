import React from 'react';
import { useAuth } from '../AuthContext';

const MENU_ITEMS = [
  {
    id: 'saved',
    label: '저장한 코스',
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
      </svg>
    ),
    disabled: true,
  },
  {
    id: 'history',
    label: '내 라이딩 기록',
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    disabled: true,
  },
  {
    id: 'settings',
    label: '설정',
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
    disabled: true,
  },
];

const MobileProfileScreen = ({ isOpen, onClose }) => {
  const { user, loginWithGoogle, logout } = useAuth();

  if (!isOpen) return null;

  return (
    <div className="md:hidden fixed inset-0 z-50 bg-gray-950 flex flex-col animate-slideUp">
      {/* Header */}
      <div className="shrink-0 flex items-center justify-between px-4 pt-[env(safe-area-inset-top)] min-h-[56px]">
        <h1 className="text-lg font-black text-white">내 정보</h1>
        <button
          onClick={onClose}
          className="w-9 h-9 flex items-center justify-center rounded-full bg-gray-800/80 active:bg-gray-700"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 pb-[env(safe-area-inset-bottom)]">
        {/* Profile Card */}
        <div className="mt-4 mb-6">
          {user ? (
            <div className="flex items-center gap-3.5 bg-gray-900 rounded-2xl p-4 border border-gray-800">
              {user.photoURL ? (
                <img
                  src={user.photoURL}
                  alt=""
                  className="w-14 h-14 rounded-full object-cover border-2 border-gray-700"
                  referrerPolicy="no-referrer"
                />
              ) : (
                <div className="w-14 h-14 rounded-full bg-gray-800 flex items-center justify-center border-2 border-gray-700">
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-7 w-7 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                </div>
              )}
              <div className="flex-1 min-w-0">
                <p className="text-white font-bold text-[15px] truncate">{user.display_name || '사용자'}</p>
                <p className="text-gray-500 text-xs truncate mt-0.5">{user.email}</p>
              </div>
            </div>
          ) : (
            <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800 text-center">
              <div className="w-16 h-16 rounded-full bg-gray-800 flex items-center justify-center mx-auto mb-3">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              </div>
              <p className="text-gray-400 text-sm font-medium mb-3">로그인하고 더 많은 기능을 이용하세요</p>
              <button
                onClick={loginWithGoogle}
                className="inline-flex items-center gap-2 bg-white text-gray-900 font-bold text-sm px-5 py-2.5 rounded-xl active:bg-gray-200 transition-colors"
              >
                <svg className="w-4 h-4" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/>
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>
                Google로 로그인
              </button>
            </div>
          )}
        </div>

        {/* Menu List */}
        <div className="bg-gray-900 rounded-2xl border border-gray-800 overflow-hidden">
          {MENU_ITEMS.map((item, index) => (
            <div
              key={item.id}
              className={`flex items-center gap-3.5 px-4 py-3.5 ${
                index < MENU_ITEMS.length - 1 ? 'border-b border-gray-800/60' : ''
              } ${item.disabled ? 'opacity-40' : 'active:bg-gray-800'}`}
            >
              <span className="text-gray-400">{item.icon}</span>
              <span className={`flex-1 text-[14px] font-medium ${item.disabled ? 'text-gray-500' : 'text-gray-200'}`}>
                {item.label}
              </span>
              {item.disabled && (
                <span className="text-[10px] font-bold text-gray-600 bg-gray-800 px-2 py-0.5 rounded-full">
                  SOON
                </span>
              )}
              {!item.disabled && (
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              )}
            </div>
          ))}
        </div>

        {/* Logout Button */}
        {user && (
          <button
            onClick={async () => {
              await logout();
              onClose();
            }}
            className="mt-4 w-full py-3 text-sm font-bold text-red-400 bg-gray-900 rounded-2xl border border-gray-800 active:bg-gray-800 transition-colors"
          >
            로그아웃
          </button>
        )}

        {/* App version */}
        <p className="text-center text-gray-700 text-[11px] mt-6 mb-4">Routy v0.1.0</p>
      </div>
    </div>
  );
};

export default MobileProfileScreen;
