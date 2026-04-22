// Tests for the reactive state store

import { describe, it, expect, beforeEach } from 'vitest';

// Inline a minimal store for testing (avoids DOM dependency in api.ts)
interface Message {
  id: string;
  role: 'user' | 'assistant' | 'error' | 'system';
  content: string;
  agent?: string;
  timestamp: number;
}

interface AppState {
  messages: Message[];
  currentAgent: string;
  isStreaming: boolean;
  streamingContent: string;
  connected: boolean;
  contextFiles: { path: string; lines?: string }[];
}

type Listener = (state: AppState) => void;

class TestStore {
  private state: AppState;
  private listeners: Set<Listener> = new Set();

  constructor() {
    this.state = {
      messages: [],
      currentAgent: 'auto-pilot',
      isStreaming: false,
      streamingContent: '',
      connected: false,
      contextFiles: [],
    };
  }

  getState(): AppState { return this.state; }

  update(partial: Partial<AppState>): void {
    this.state = { ...this.state, ...partial };
    this.notify();
  }

  addMessage(msg: Message): void {
    this.state = { ...this.state, messages: [...this.state.messages, msg] };
    this.notify();
  }

  updateLastMessage(content: string): void {
    const msgs = [...this.state.messages];
    if (msgs.length > 0) {
      msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content };
    }
    this.state = { ...this.state, messages: msgs };
    this.notify();
  }

  clearMessages(): void {
    this.state = { ...this.state, messages: [] };
    this.notify();
  }

  addContextFile(path: string, lines?: string): void {
    const exists = this.state.contextFiles.some(f => f.path === path);
    if (!exists) {
      this.state = { ...this.state, contextFiles: [...this.state.contextFiles, { path, lines }] };
      this.notify();
    }
  }

  removeContextFile(path: string): void {
    this.state = { ...this.state, contextFiles: this.state.contextFiles.filter(f => f.path !== path) };
    this.notify();
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(): void {
    for (const listener of this.listeners) {
      listener(this.state);
    }
  }
}

describe('Store', () => {
  let store: TestStore;

  beforeEach(() => {
    store = new TestStore();
  });

  it('initializes with default state', () => {
    const state = store.getState();
    expect(state.currentAgent).toBe('auto-pilot');
    expect(state.messages).toEqual([]);
    expect(state.isStreaming).toBe(false);
    expect(state.connected).toBe(false);
  });

  it('updates partial state', () => {
    store.update({ currentAgent: 'code-reviewer', connected: true });
    const state = store.getState();
    expect(state.currentAgent).toBe('code-reviewer');
    expect(state.connected).toBe(true);
    expect(state.messages).toEqual([]); // unchanged
  });

  it('adds messages', () => {
    store.addMessage({ id: '1', role: 'user', content: 'hello', timestamp: 1000 });
    store.addMessage({ id: '2', role: 'assistant', content: 'hi', agent: 'auto-pilot', timestamp: 1001 });
    expect(store.getState().messages).toHaveLength(2);
    expect(store.getState().messages[0].content).toBe('hello');
    expect(store.getState().messages[1].agent).toBe('auto-pilot');
  });

  it('updates last message content (streaming)', () => {
    store.addMessage({ id: '1', role: 'assistant', content: '', timestamp: 1000 });
    store.updateLastMessage('Hello');
    store.updateLastMessage('Hello world');
    expect(store.getState().messages[0].content).toBe('Hello world');
  });

  it('handles updateLastMessage on empty messages gracefully', () => {
    store.updateLastMessage('test');
    expect(store.getState().messages).toHaveLength(0);
  });

  it('clears messages', () => {
    store.addMessage({ id: '1', role: 'user', content: 'test', timestamp: 1000 });
    store.clearMessages();
    expect(store.getState().messages).toHaveLength(0);
  });

  it('notifies subscribers on state change', () => {
    let notified = 0;
    store.subscribe(() => { notified++; });
    store.update({ connected: true });
    store.addMessage({ id: '1', role: 'user', content: 'x', timestamp: 1 });
    expect(notified).toBe(2);
  });

  it('unsubscribes correctly', () => {
    let notified = 0;
    const unsub = store.subscribe(() => { notified++; });
    store.update({ connected: true });
    unsub();
    store.update({ connected: false });
    expect(notified).toBe(1);
  });

  it('adds context files without duplicates', () => {
    store.addContextFile('src/app.ts', 'lines 1-10');
    store.addContextFile('src/app.ts', 'lines 1-10'); // duplicate
    store.addContextFile('src/index.ts');
    expect(store.getState().contextFiles).toHaveLength(2);
  });

  it('removes context files', () => {
    store.addContextFile('src/app.ts');
    store.addContextFile('src/index.ts');
    store.removeContextFile('src/app.ts');
    expect(store.getState().contextFiles).toHaveLength(1);
    expect(store.getState().contextFiles[0].path).toBe('src/index.ts');
  });
});
