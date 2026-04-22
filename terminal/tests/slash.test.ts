import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SLASH_REGISTRY, dispatchSlash } from '../src/slash/index.js';
import type { SlashContext } from '../src/slash/index.js';

// Mock fetch globally
const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

function makeCtx(overrides?: Partial<SlashContext>): SlashContext {
  return {
    store: {
      agent: 'auto-pilot',
      sessionId: 'test-session-123',
      repoPath: '/tmp/test-repo',
      mode: 'chat',
      messages: [
        { role: 'user', content: 'hello' },
        { role: 'assistant', content: 'hi' },
      ],
      messageQueue: [],
      isBusy: false,
      superpower: false,
      tokenUsage: { input: 100, output: 200, cached: 10 },
      cycleMode: vi.fn(),
      setAgent: vi.fn(),
      addMessage: vi.fn(),
      enqueueMessage: vi.fn(),
      dequeueMessage: vi.fn(),
      setSessionId: vi.fn(),
      setBusy: vi.fn(),
      updateTokens: vi.fn(),
      reset: vi.fn(),
    } as any,
    client: {
      getServerUrl: () => 'http://localhost:8000',
    } as any,
    agentService: {
      currentAgent: 'auto-pilot',
      getAgents: () => [
        { name: 'auto-pilot', description: 'Main agent' },
        { name: 'code-reviewer', description: 'Review code' },
      ],
      getAgentNames: () => ['auto-pilot', 'code-reviewer'],
      setAgent: vi.fn().mockReturnValue(true),
    } as any,
    ...overrides,
  };
}

describe('Slash Registry', () => {
  it('should have commands registered', () => {
    expect(SLASH_REGISTRY.size).toBeGreaterThan(0);
  });

  it('should have help command', () => {
    expect(SLASH_REGISTRY.has('help')).toBe(true);
  });

  it('should have aliases registered', () => {
    // /quit has aliases /exit and /q
    expect(SLASH_REGISTRY.has('exit')).toBe(true);
    expect(SLASH_REGISTRY.has('q')).toBe(true);
  });
});

describe('dispatchSlash', () => {
  let ctx: SlashContext;

  beforeEach(() => {
    ctx = makeCtx();
    mockFetch.mockReset();
  });

  it('should return unknown for non-slash input', async () => {
    const result = await dispatchSlash('hello', ctx);
    expect(result.action).toBe('continue');
    expect((result as any).output).toContain('Not a slash command');
  });

  it('should return unknown for unknown command', async () => {
    const result = await dispatchSlash('/nonexistent', ctx);
    expect(result.action).toBe('continue');
    expect((result as any).output).toContain('Unknown command');
  });

  it('should handle /quit', async () => {
    const result = await dispatchSlash('/quit', ctx);
    expect(result.action).toBe('quit');
  });

  it('should handle /exit alias', async () => {
    const result = await dispatchSlash('/exit', ctx);
    expect(result.action).toBe('quit');
  });

  it('should handle /help', async () => {
    const result = await dispatchSlash('/help', ctx);
    expect(result.action).toBe('continue');
    expect((result as any).output).toContain('Slash Commands');
  });

  it('should handle /clear', async () => {
    const result = await dispatchSlash('/clear', ctx);
    expect(result.action).toBe('continue');
    expect((result as any).output).toContain('cleared');
    expect(ctx.store.reset).toHaveBeenCalled();
  });

  it('should handle /session', async () => {
    const result = await dispatchSlash('/session', ctx);
    expect(result.action).toBe('continue');
    expect((result as any).output).toContain('auto-pilot');
    expect((result as any).output).toContain('test-session-123');
  });

  it('should handle /tokens', async () => {
    const result = await dispatchSlash('/tokens', ctx);
    expect(result.action).toBe('continue');
    expect((result as any).output).toContain('100');
    expect((result as any).output).toContain('200');
  });

  it('should handle /agents', async () => {
    const result = await dispatchSlash('/agents', ctx);
    expect(result.action).toBe('continue');
    expect((result as any).output).toContain('auto-pilot');
    expect((result as any).output).toContain('code-reviewer');
  });

  it('should handle /agent with valid name', async () => {
    const result = await dispatchSlash('/agent code-reviewer', ctx);
    expect(result.action).toBe('switch_agent');
    expect((result as any).agent).toBe('code-reviewer');
  });

  it('should handle /agent with no arg', async () => {
    const result = await dispatchSlash('/agent', ctx);
    expect(result.action).toBe('continue');
    expect((result as any).output).toContain('Current agent');
  });

  it('should handle /repo', async () => {
    const result = await dispatchSlash('/repo', ctx);
    expect(result.action).toBe('continue');
    expect((result as any).output).toContain('/tmp/test-repo');
  });

  it('should handle /run without superpower', async () => {
    const result = await dispatchSlash('/run ls', ctx);
    expect(result.action).toBe('continue');
    expect((result as any).output).toContain('Superpower mode is off');
  });

  it('should handle /theme with no arg', async () => {
    const result = await dispatchSlash('/theme', ctx);
    expect(result.action).toBe('continue');
    expect((result as any).output).toContain('dark');
  });

  it('should handle /theme with valid theme', async () => {
    const result = await dispatchSlash('/theme monokai', ctx);
    expect(result.action).toBe('continue');
    expect((result as any).output).toContain('monokai');
  });

  it('should handle /theme with invalid theme', async () => {
    const result = await dispatchSlash('/theme nope', ctx);
    expect(result.action).toBe('continue');
    expect((result as any).output).toContain('Unknown theme');
  });

  it('should handle /resume with no arg', async () => {
    const result = await dispatchSlash('/resume', ctx);
    expect(result.action).toBe('continue');
    expect((result as any).output).toContain('Usage');
  });

  it('should handle /resume with session id', async () => {
    const result = await dispatchSlash('/resume abc-123', ctx);
    expect(result.action).toBe('continue');
    expect((result as any).output).toContain('Resumed session abc-123');
    expect(ctx.store.setSessionId).toHaveBeenCalledWith('abc-123');
  });

  it('should handle /plan with no arg (mode cycle)', async () => {
    const result = await dispatchSlash('/plan', ctx);
    expect(result.action).toBe('continue');
    expect(ctx.store.cycleMode).toHaveBeenCalled();
  });

  it('should handle /plan with arg (send)', async () => {
    const result = await dispatchSlash('/plan refactor the auth module', ctx);
    expect(result.action).toBe('send');
    expect((result as any).message).toContain('[PLAN]');
  });

  it('should handle /model with no arg', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ model: 'gpt-4' }),
    });
    const result = await dispatchSlash('/model', ctx);
    expect(result.action).toBe('continue');
    expect((result as any).output).toContain('gpt-4');
  });

  it('should handle /backend with invalid value', async () => {
    const result = await dispatchSlash('/backend invalid', ctx);
    expect(result.action).toBe('continue');
    expect((result as any).output).toContain('Invalid backend');
  });
});
