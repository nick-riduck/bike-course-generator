import React from 'react';
import { useAuth } from '../AuthContext';

const Login = () => {
  const { loginWithGoogle, user, logout } = useAuth();

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
        {user.profile_image_url && (
          <img 
            src={user.profile_image_url} 
            alt="profile" 
            className="w-8 h-8 rounded-full border border-riduck-primary"
          />
        )}
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
