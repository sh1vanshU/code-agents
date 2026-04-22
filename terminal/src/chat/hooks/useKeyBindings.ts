/**
 * useKeyBindings — Keyboard shortcuts for the chat REPL.
 *
 * - Shift+Tab: cycle mode (chat -> plan -> edit -> chat)
 * - Ctrl+C: cancel stream or exit
 * - Escape: clear input (handled via callback)
 */

import { useInput, useApp } from 'ink';
import { useChatStore } from '../../state/store.js';

interface Options {
  isStreaming: boolean;
  cancelStream: () => void;
  clearInput: () => void;
}

export function useKeyBindings({ isStreaming, cancelStream, clearInput }: Options): void {
  const { exit } = useApp();
  const cycleMode = useChatStore((s) => s.cycleMode);

  useInput((_input, key) => {
    // Shift+Tab — cycle mode
    if (key.shift && key.tab) {
      cycleMode();
      return;
    }

    // Ctrl+C — cancel or exit
    if (key.ctrl && _input === 'c') {
      if (isStreaming) {
        cancelStream();
      } else {
        exit();
      }
      return;
    }

    // Escape — clear input
    if (key.escape) {
      clearInput();
    }
  });
}
