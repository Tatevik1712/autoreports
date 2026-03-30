import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { UserRead } from '@/types';

interface AuthState {
  token: string | null;
  user: UserRead | null;
  isAuthenticated: boolean;
  setAuth: (token: string, user: UserRead) => void;
  clearAuth: () => void;
  setUser: (user: UserRead) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      isAuthenticated: false,
      setAuth: (token, user) => set({ token, user, isAuthenticated: true }),
      clearAuth: () => set({ token: null, user: null, isAuthenticated: false }),
      setUser: (user) => set({ user }),
    }),
    {
      name: 'autoreports-auth',
      partialize: (state) => ({ token: state.token, user: state.user, isAuthenticated: state.isAuthenticated }),
    }
  )
);
