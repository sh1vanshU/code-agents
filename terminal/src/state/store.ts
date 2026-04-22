/**
 * Code Agents — Zustand Chat Store
 *
 * Central state for the terminal client: current agent, session, messages,
 * mode cycling (chat/plan/edit), message queue, and token tracking.
 */

import { create } from 'zustand';
import type { ChatMessage } from '../client/types.js';

const MODES = ['chat', 'plan', 'edit'] as const;
type Mode = (typeof MODES)[number];

export const MAX_QUEUE_SIZE = 5;

export interface ChatStore {
  agent: string;
  sessionId: string | null;
  repoPath: string;
  mode: Mode;
  messages: ChatMessage[];
  messageQueue: string[];
  isBusy: boolean;
  superpower: boolean;
  tokenUsage: { input: number; output: number; cached: number };

  // Actions
  cycleMode: () => void;
  setAgent: (name: string) => void;
  addMessage: (msg: ChatMessage) => void;
  enqueueMessage: (text: string) => boolean;
  dequeueMessage: () => string | undefined;
  setSessionId: (id: string) => void;
  setBusy: (busy: boolean) => void;
  updateTokens: (usage: { input: number; output: number; cached?: number }) => void;
  reset: () => void;
}

export const useChatStore = create<ChatStore>((set, get) => ({
  agent: 'auto-pilot',
  sessionId: null,
  repoPath: process.env['CODE_AGENTS_USER_CWD'] || process.env['TARGET_REPO_PATH'] || process.cwd(),
  mode: 'chat',
  messages: [],
  messageQueue: [],
  isBusy: false,
  superpower: false,
  tokenUsage: { input: 0, output: 0, cached: 0 },

  cycleMode: () =>
    set((state) => {
      const idx = MODES.indexOf(state.mode);
      return { mode: MODES[(idx + 1) % MODES.length] };
    }),

  setAgent: (name: string) => set({ agent: name }),

  addMessage: (msg: ChatMessage) =>
    set((state) => ({ messages: [...state.messages, msg] })),

  enqueueMessage: (text: string) => {
    const state = get();
    if (state.messageQueue.length >= MAX_QUEUE_SIZE) {
      return false; // queue full — caller should show error
    }
    set({ messageQueue: [...state.messageQueue, text] });
    return true;
  },

  dequeueMessage: () => {
    const queue = get().messageQueue;
    if (queue.length === 0) return undefined;
    const [first, ...rest] = queue;
    set({ messageQueue: rest });
    return first;
  },

  setSessionId: (id: string) => set({ sessionId: id }),

  setBusy: (busy: boolean) => set({ isBusy: busy }),

  updateTokens: (usage) =>
    set((state) => ({
      tokenUsage: {
        input: state.tokenUsage.input + usage.input,
        output: state.tokenUsage.output + usage.output,
        cached: state.tokenUsage.cached + (usage.cached ?? 0),
      },
    })),

  reset: () =>
    set({
      sessionId: null,
      messages: [],
      messageQueue: [],
      isBusy: false,
      tokenUsage: { input: 0, output: 0, cached: 0 },
    }),
}));
