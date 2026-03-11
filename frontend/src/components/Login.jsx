import React, { useState, useRef, useEffect } from 'react';
import { useAuth } from '../AuthContext';

const Login = () => {
  const { loginWithGoogle, user, logout } = useAuth();
  const [profileOpen, setProfileOpen] = useState(false);
  const profileRef = useRef(null);

  const isProfileIncomplete = user && !user.username;

  useEffect(() => {
    if (!profileOpen) return;
    const handleClickOutside = (e) => {
      if (profileRef.current && !profileRef.current.contains(e.target)) {
        setProfileOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, [profileOpen]);

  if (user) {
    return (
      <div className="flex items-center gap-3">
        <div className="flex flex-col items-end">
          <span className="text-sm font-bold text-white">{user.username}</span>
          <button
            onClick={logout}
            className="text-[10px] text-gray-400 hover:text-white underline"
          >
            Logout
          </button>
        </div>
        <div className="relative" ref={profileRef}>
          <button
            onClick={() => setProfileOpen(!profileOpen)}
            className="relative focus:outline-none"
          >
            {user.profile_image_url ? (
              <img
                src={user.profile_image_url}
                alt="profile"
                className="w-8 h-8 rounded-full border border-routy-primary"
              />
            ) : (
              <div className="w-8 h-8 rounded-full border border-routy-primary bg-gray-700 flex items-center justify-center text-white text-sm font-bold">
                {(user.username || '?')[0].toUpperCase()}
              </div>
            )}
            {isProfileIncomplete && (
              <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-red-500 rounded-full border-2 border-gray-900" />
            )}
          </button>
          {profileOpen && (
            <div className="absolute top-full mt-2 right-0 bg-gray-900/95 border border-gray-700 rounded-xl shadow-2xl backdrop-blur-md overflow-hidden animate-fade-in-up min-w-[200px] z-50">
              <div className="px-4 py-3 border-b border-gray-700/50">
                <div className="flex items-center gap-3">
                  {user.profile_image_url ? (
                    <img src={user.profile_image_url} alt="profile" className="w-10 h-10 rounded-full border border-routy-primary" />
                  ) : (
                    <div className="w-10 h-10 rounded-full border border-routy-primary bg-gray-700 flex items-center justify-center text-white text-lg font-bold">
                      {(user.username || '?')[0].toUpperCase()}
                    </div>
                  )}
                  <div className="min-w-0">
                    <p className="text-sm font-bold text-white truncate">{user.username || 'Unknown'}</p>
                    <p className="text-[11px] text-gray-400 truncate">{user.email || ''}</p>
                  </div>
                </div>
              </div>
              <div className="px-4 py-3">
                <p className="text-xs text-gray-500 text-center">프로필 편집 - 준비 중</p>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <button
      onClick={loginWithGoogle}
      className="p-2 md:px-4 md:py-2 bg-white text-black font-bold rounded-full md:rounded-lg hover:bg-gray-200 transition-colors flex items-center gap-2 shadow-lg"
      aria-label="Login with Google"
    >
      <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" alt="G" className="w-5 h-5" />
      <span className="hidden md:inline">Sign in with Google</span>
    </button>
  );
};

export default Login;
