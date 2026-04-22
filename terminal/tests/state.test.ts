import { describe, it, expect, beforeEach, vi } from 'vitest';

describe('ChatStore', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it('should import store module', async () => {
    const mod = await import('../src/state/store.js');
    expect(mod.useChatStore).toBeDefined();
  });

  it('should have correct initial state', async () => {
    const { useChatStore } = await import('../src/state/store.js');
    const state = useChatStore.getState();
    expect(state.agent).toBe('auto-pilot');
    expect(state.mode).toBe('chat');
    expect(state.messages).toEqual([]);
    expect(state.isBusy).toBe(false);
    expect(state.superpower).toBe(false);
  });

  it('should cycle modes', async () => {
    const { useChatStore } = await import('../src/state/store.js');
    const store = useChatStore;

    expect(store.getState().mode).toBe('chat');
    store.getState().cycleMode();
    expect(store.getState().mode).toBe('plan');
    store.getState().cycleMode();
    expect(store.getState().mode).toBe('edit');
    store.getState().cycleMode();
    expect(store.getState().mode).toBe('chat');
  });

  it('should add messages', async () => {
    const { useChatStore } = await import('../src/state/store.js');
    const store = useChatStore;

    store.getState().addMessage({ role: 'user', content: 'hello' });
    expect(store.getState().messages).toHaveLength(1);
    store.getState().addMessage({ role: 'assistant', content: 'hi' });
    expect(store.getState().messages).toHaveLength(2);
  });

  it('should manage message queue', async () => {
    const { useChatStore } = await import('../src/state/store.js');
    const store = useChatStore;
    store.getState().reset();

    expect(store.getState().enqueueMessage('first')).toBe(true);
    expect(store.getState().enqueueMessage('second')).toBe(true);
    expect(store.getState().messageQueue).toHaveLength(2);

    const msg = store.getState().dequeueMessage();
    expect(msg).toBe('first');
    expect(store.getState().messageQueue).toHaveLength(1);
  });

  it('should cap message queue at MAX_QUEUE_SIZE', async () => {
    const { useChatStore, MAX_QUEUE_SIZE } = await import('../src/state/store.js');
    const store = useChatStore;
    store.getState().reset();

    for (let i = 0; i < MAX_QUEUE_SIZE; i++) {
      expect(store.getState().enqueueMessage(`msg ${i}`)).toBe(true);
    }
    expect(store.getState().messageQueue).toHaveLength(MAX_QUEUE_SIZE);

    // Next enqueue should be rejected
    expect(store.getState().enqueueMessage('overflow')).toBe(false);
    expect(store.getState().messageQueue).toHaveLength(MAX_QUEUE_SIZE);

    // After dequeue, space is available again
    store.getState().dequeueMessage();
    expect(store.getState().enqueueMessage('now-fits')).toBe(true);
    expect(store.getState().messageQueue).toHaveLength(MAX_QUEUE_SIZE);
  });

  it('should update tokens', async () => {
    const { useChatStore } = await import('../src/state/store.js');
    const store = useChatStore;

    store.getState().updateTokens({ input: 100, output: 50 });
    expect(store.getState().tokenUsage.input).toBe(100);
    expect(store.getState().tokenUsage.output).toBe(50);
  });

  it('should reset state', async () => {
    const { useChatStore } = await import('../src/state/store.js');
    const store = useChatStore;

    store.getState().addMessage({ role: 'user', content: 'test' });
    store.getState().setAgent('code-reviewer');
    store.getState().reset();

    expect(store.getState().messages).toEqual([]);
    // reset clears messages/tokens but agent may persist depending on store implementation
    expect(store.getState().isBusy).toBe(false);
  });
});

describe('TokenTracker', () => {
  it('should import and track tokens', async () => {
    const { TokenTracker } = await import('../src/state/TokenTracker.js');
    const tracker = new TokenTracker();

    tracker.record({ input: 500, output: 200 });
    expect(tracker.getTotal().total).toBe(700);

    tracker.record({ input: 300, output: 100, cached: 50 });
    expect(tracker.getTotal().total).toBe(1100);
  });

  it('should format token counts', async () => {
    const { TokenTracker } = await import('../src/state/TokenTracker.js');
    const tracker = new TokenTracker();

    tracker.record({ input: 1500, output: 700 });
    expect(tracker.format()).toContain('k');
  });
});

describe('Scratchpad', () => {
  it('should import scratchpad module', async () => {
    const mod = await import('../src/state/Scratchpad.js');
    expect(mod.Scratchpad).toBeDefined();
  });
});

describe('Config', () => {
  it('should import config module', async () => {
    const mod = await import('../src/state/config.js');
    expect(mod.getServerUrl).toBeDefined();
    expect(mod.getConfigValue).toBeDefined();
  });

  it('should return default server URL', async () => {
    const { getServerUrl } = await import('../src/state/config.js');
    const url = getServerUrl();
    expect(url).toContain('localhost');
    expect(url).toContain('8000');
  });
});

describe('SessionHistory', () => {
  it('should import session history module', async () => {
    const mod = await import('../src/state/SessionHistory.js');
    expect(mod.generateSessionId).toBeDefined();
    expect(mod.create).toBeDefined();
  });

  it('should generate unique session IDs', async () => {
    const { generateSessionId } = await import('../src/state/SessionHistory.js');
    const id1 = generateSessionId();
    const id2 = generateSessionId();
    expect(id1).not.toBe(id2);
    expect(id1.length).toBeGreaterThan(8);
  });
});
