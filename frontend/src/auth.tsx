import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { api, ApiError, errorMessage } from './api';
import type { User } from './types';

interface AuthState { user: User | null; loading: boolean; error?: string; retry: () => Promise<void>; setUser: (user: User | null) => void }
const AuthContext = createContext<AuthState>({ user: null, loading: true, retry: async () => undefined, setUser: () => undefined });
export const useAuth = () => useContext(AuthContext);
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const active = useRef(true);
  const sequence = useRef(0);
  const retry = useCallback(async () => {
    const current = ++sequence.current;
    setLoading(true); setError(undefined);
    try {
      const account = await api<User>('/auth/me');
      if (active.current && current === sequence.current) setUser(account);
    } catch (error) {
      if (active.current && current === sequence.current) {
        if (error instanceof ApiError && error.status === 401) setUser(null);
        else setError(errorMessage(error));
      }
    } finally { if (active.current && current === sequence.current) setLoading(false); }
  }, []);
  useEffect(() => {
    active.current = true;
    void retry();
    const expired = () => { sequence.current += 1; setUser(null); setError(undefined); setLoading(false); };
    window.addEventListener('auth-expired', expired);
    return () => { active.current = false; window.removeEventListener('auth-expired', expired); };
  }, [retry]);
  return <AuthContext.Provider value={{ user, setUser, loading, error, retry }}>{children}</AuthContext.Provider>;
}
