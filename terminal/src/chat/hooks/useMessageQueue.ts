/**
 * useMessageQueue — Queue input while the agent is busy.
 *
 * Messages are enqueued in the store and auto-dequeued when the
 * agent finishes processing (isBusy transitions from true to false).
 */

import { useEffect, useRef, useCallback } from 'react';
import { useChatStore } from '../../state/store.js';

interface Options {
  onDequeue: (text: string) => void;
}

export function useMessageQueue({ onDequeue }: Options) {
  const isBusy = useChatStore((s) => s.isBusy);
  const enqueueMessage = useChatStore((s) => s.enqueueMessage);
  const dequeueMessage = useChatStore((s) => s.dequeueMessage);
  const prevBusyRef = useRef(isBusy);

  // When busy transitions from true -> false, dequeue next message
  useEffect(() => {
    if (prevBusyRef.current && !isBusy) {
      const next = dequeueMessage();
      if (next) {
        onDequeue(next);
      }
    }
    prevBusyRef.current = isBusy;
  }, [isBusy, dequeueMessage, onDequeue]);

  const enqueue = useCallback((text: string): boolean => {
    return enqueueMessage(text);
  }, [enqueueMessage]);

  return { enqueue };
}
