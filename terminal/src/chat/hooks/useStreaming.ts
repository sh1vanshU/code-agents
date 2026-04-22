/**
 * useStreaming — SSE streaming React hook.
 *
 * Wraps ApiClient.streamChat() async generator, providing reactive
 * state for content, streaming status, and errors. Handles abort
 * and cleanup on unmount.
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import type { ApiClient } from '../../client/ApiClient.js';
import type { ChatMessage, StreamEvent } from '../../client/types.js';

export interface StreamingState {
  content: string;
  isStreaming: boolean;
  error: string | null;
  usage: { prompt_tokens: number; completion_tokens: number; cached_tokens?: number } | undefined;
  durationMs: number | undefined;
  sessionId: string | undefined;
}

export interface UseStreamingReturn extends StreamingState {
  start: (agent: string, messages: ChatMessage[], options?: { sessionId?: string; cwd?: string }) => Promise<StreamEvent | null>;
  cancel: () => void;
}

export function useStreaming(client: ApiClient): UseStreamingReturn {
  const [content, setContent] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [usage, setUsage] = useState<StreamingState['usage']>(undefined);
  const [durationMs, setDurationMs] = useState<number | undefined>(undefined);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);

  const cancelledRef = useRef(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const cancel = useCallback(() => {
    cancelledRef.current = true;
    client.cancelStream();
  }, [client]);

  const start = useCallback(async (
    agent: string,
    messages: ChatMessage[],
    options?: { sessionId?: string; cwd?: string },
  ): Promise<StreamEvent | null> => {
    cancelledRef.current = false;
    setContent('');
    setError(null);
    setUsage(undefined);
    setDurationMs(undefined);
    setSessionId(undefined);
    setIsStreaming(true);

    let lastDoneEvent: StreamEvent | null = null;
    let accumulated = '';
    let lastFlush = 0;
    const FLUSH_INTERVAL_MS = 80; // ~12 fps — smooth but cheap

    const flush = () => {
      if (mountedRef.current) setContent(accumulated);
      lastFlush = Date.now();
    };

    try {
      for await (const event of client.streamChat(agent, messages, options)) {
        if (!mountedRef.current || cancelledRef.current) break;

        switch (event.type) {
          case 'token':
            accumulated += event.content;
            // Throttle React updates — avoids re-parsing markdown on every token
            if (Date.now() - lastFlush >= FLUSH_INTERVAL_MS) {
              flush();
            }
            break;
          case 'done':
            flush(); // final flush to show last tokens
            lastDoneEvent = event;
            if (event.usage) setUsage(event.usage);
            if (event.durationMs) setDurationMs(event.durationMs);
            if (event.sessionId) setSessionId(event.sessionId);
            break;
          case 'error':
            setError(event.message);
            break;
        }
      }
    } catch (err: any) {
      if (mountedRef.current) {
        setError(err.message ?? 'Stream failed');
      }
    } finally {
      // Final flush on stream end to ensure all accumulated tokens are visible
      if (mountedRef.current && accumulated) {
        setContent(accumulated);
      }
      if (mountedRef.current) {
        setIsStreaming(false);
      }
    }

    return lastDoneEvent;
  }, [client]);

  return { content, isStreaming, error, usage, durationMs, sessionId, start, cancel };
}
