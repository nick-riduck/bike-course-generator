import React, { createContext, useContext, useEffect, useState } from 'react';
import { auth, googleProvider } from './firebase';
import { signInWithPopup, onAuthStateChanged, signOut } from 'firebase/auth';

const AuthContext = createContext();

export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState(null);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      setAuthError(null);
      try {
        if (firebaseUser) {
          const idToken = await firebaseUser.getIdToken();
          const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id_token: idToken }),
          });
          
          if (response.ok) {
            const data = await response.json();
            setUser(data.user);
          } else {
            console.error('Backend login failed');
            setAuthError("Server login failed. Please try again.");
            setUser(null);
          }
        } else {
          setUser(null);
        }
      } catch (error) {
        console.error('Error during backend auth:', error);
        setAuthError("Could not connect to authentication server.");
        setUser(null);
      } finally {
        setLoading(false);
      }
    });

    return unsubscribe;
  }, [retryCount]);

  const loginWithGoogle = async () => {
    try {
      await signInWithPopup(auth, googleProvider);
    } catch (error) {
      console.error('Google login error:', error);
    }
  };

  const logout = async () => {
    try {
      await signOut(auth);
      setUser(null);
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  const handleRetry = () => {
      setLoading(true);
      setRetryCount(prev => prev + 1);
  };

  const value = {
    user,
    loading,
    loginWithGoogle,
    logout
  };

  if (loading) {
      return (
        <div className="h-screen flex flex-col items-center justify-center bg-gray-900 text-white gap-4">
            <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-riduck-primary"></div>
            <p className="text-sm font-bold animate-pulse">Initializing App...</p>
        </div>
      );
  }

  if (authError) {
      return (
        <div className="h-screen flex flex-col items-center justify-center bg-gray-900 text-white p-8 text-center gap-6">
            <div className="text-6xl">⚠️</div>
            <div>
                <h1 className="text-xl font-black mb-2">Connectivity Issue</h1>
                <p className="text-gray-400 text-sm max-w-xs mx-auto">{authError}</p>
            </div>
            <div className="flex gap-3">
                <button 
                    onClick={handleRetry}
                    className="bg-riduck-primary hover:brightness-110 text-white px-6 py-3 rounded-2xl font-bold transition-all shadow-lg shadow-riduck-primary/20"
                >
                    RETRY CONNECTION
                </button>
                <button 
                    onClick={() => setAuthError(null)}
                    className="bg-gray-800 hover:bg-gray-700 text-gray-300 px-6 py-3 rounded-2xl font-bold transition-all"
                >
                    CONTINUE AS GUEST
                </button>
            </div>
        </div>
      );
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};
