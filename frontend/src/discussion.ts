import { useEffect, useRef, useState } from 'react';
import { api, errorMessage } from './api';
import type { ChatMessage, GroupDetail } from './types';

export function mergeMessages(previous: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
  const unique = new Map(previous.map(message => [message.id, message]));
  incoming.forEach(message => unique.set(message.id, message));
  return [...unique.values()].sort((a, b) => a.created_at - b.created_at || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
}

export function useDiscussionMessages(group: GroupDetail | undefined) {
  const [cache, setCache] = useState<{ groupId: string; items: ChatMessage[] }>();
  const [error, setError] = useState<string>();
  const [recovering, setRecovering] = useState(false);
  const retained = useRef(cache);
  retained.current = cache;
  useEffect(() => {
    if (!group) return;
    let cancelled = false;
    const previous = retained.current?.groupId === group.id ? retained.current.items : [];
    const last = previous.at(-1);
    const first = group.messages[0];
    const gap = last && first && !group.messages.some(message => message.id === last.id)
      && (first.created_at > last.created_at || (first.created_at === last.created_at && first.id > last.id));
    const retain = (incoming: ChatMessage[]) => setCache(current => ({
      groupId: group.id,
      items: mergeMessages(current?.groupId === group.id ? current.items : [], incoming),
    }));
    const recover = async () => {
      if (gap) {
        setRecovering(true);
        let cursor = last.id;
        while (!cancelled) {
          const page = await api<ChatMessage[]>(`/groups/${group.id}/messages?after_id=${encodeURIComponent(cursor)}&limit=200`);
          if (cancelled) return;
          retain(page);
          if (page.length < 200) break;
          cursor = page[page.length - 1].id;
        }
      }
      if (!cancelled) { retain(group.messages); setError(undefined); }
    };
    void recover().catch(error => { if (!cancelled) setError(errorMessage(error)); })
      .finally(() => { if (!cancelled) setRecovering(false); });
    return () => { cancelled = true; };
  }, [group?.id, group?.messages]);
  const appendHistory = (items: ChatMessage[]) => {
    if (!group) return;
    setCache(previous => ({ groupId: group.id, items: mergeMessages(previous?.groupId === group.id ? previous.items : [], items) }));
  };
  return { messages: mergeMessages(cache?.groupId === group?.id ? cache?.items || [] : [], group?.messages || []), appendHistory, recovering, error };
}
