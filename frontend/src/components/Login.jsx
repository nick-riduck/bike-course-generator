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
      className="px-4 py-2 bg-white text-black font-bold rounded-lg hover:bg-gray-200 transition-colors flex items-center gap-2"
    >
      <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" alt="G" className="w-4 h-4" />
      <span className="hidden md:inline">Google Login</span>
      <span className="md:hidden">Login</span>
    </button>
  );
};

export default Login;
