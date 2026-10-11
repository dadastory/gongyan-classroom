import { useCallback, useEffect, useRef, useState } from 'react';

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    credentials: 'include', ...options,
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: '请求失败，请稍后重试' }));
    const detail = Array.isArray(body.detail)
      ? body.detail.map((item: { msg: string }) => item.msg).join('；') : body.detail || '请求失败';
    if (response.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('auth-expired'));
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export function send<T>(path: string, body?: unknown, method = 'POST'): Promise<T> {
  return api<T>(path, { method, ...(body !== undefined ? { body: JSON.stringify(body) } : {}) });
}

export function useResource<T>(path: string | null) {
  const [record, setRecord] = useState<{ path: string; data: T }>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const requestSequence = useRef(0);
  const currentPath = useRef(path);
  currentPath.current = path;
  const refresh = useCallback(async () => {
    if (!path) { setLoading(false); return; }
    const sequence = ++requestSequence.current;
    try {
      const result = await api<T>(path);
      if (sequence === requestSequence.current && currentPath.current === path) {
        setRecord({ path, data: result }); setError(undefined);
      }
    } catch (error) {
      if (sequence === requestSequence.current && currentPath.current === path) {
        setError(errorMessage(error));
        if (error instanceof ApiError && [401, 403, 404].includes(error.status)) setRecord(undefined);
      }
    } finally {
      if (sequence === requestSequence.current && currentPath.current === path) setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    setRecord(undefined); setError(undefined); setLoading(true); void refresh();
    return () => { requestSequence.current += 1; };
  }, [refresh]);
  return { data: record?.path === path ? record.data : undefined, loading, error, refresh };
}

export function useTopicLive(topicId: string | undefined, refresh: () => Promise<unknown>) {
  const [connected, setConnected] = useState(false);
  const callback = useRef(refresh);
  callback.current = refresh;
  useEffect(() => {
    setConnected(false);
    if (!topicId) return;
    let socket: WebSocket;
    let retry: ReturnType<typeof setTimeout>;
    let stopped = false;
    let failures = 0;
    let accessRevoked = false;
    let refreshing = false;
    let refreshAgain = false;
    let scheduled: ReturnType<typeof setTimeout> | undefined;
    const refreshNow = async () => {
      if (stopped) return;
      if (refreshing) { refreshAgain = true; return; }
      refreshing = true;
      try { await callback.current(); }
      finally {
        refreshing = false;
        if (refreshAgain && !stopped) { refreshAgain = false; void refreshNow(); }
      }
    };
    const schedule = () => {
      if (!scheduled) scheduled = setTimeout(() => { scheduled = undefined; void refreshNow(); }, 150);
    };
    const connect = () => {
      socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/ws/topics/${topicId}`);
      socket.onopen = () => { failures = 0; setConnected(true); void refreshNow(); };
      socket.onmessage = event => {
        try {
          const message = JSON.parse(event.data) as { type: string };
          if (message.type !== 'pong') schedule();
        } catch { schedule(); }
      };
      socket.onclose = event => {
        if (stopped) return;
        setConnected(false);
        if (event.code === 4401) { window.dispatchEvent(new Event('auth-expired')); return; }
        if (event.code === 4403) { accessRevoked = true; void refreshNow(); return; }
        if (!stopped) retry = setTimeout(connect, Math.min(15000, 1000 * 2 ** failures++));
      };
    };
    connect();
    const heartbeat = setInterval(() => { if (socket.readyState === WebSocket.OPEN) socket.send('ping'); }, 20000);
    const fallback = setInterval(() => { if (!accessRevoked) void refreshNow(); }, 15000);
    return () => { stopped = true; clearTimeout(retry); clearTimeout(scheduled); clearInterval(heartbeat); clearInterval(fallback); socket.close(); };
  }, [topicId]);
  return connected;
}

export function errorMessage(error: unknown): string {
  if (error instanceof TypeError && /fetch|network/i.test(error.message)) return '网络连接暂不可用，请检查网络后重试';
  return error instanceof Error ? error.message : '操作失败，请稍后重试';
}

export function newClientId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
}
