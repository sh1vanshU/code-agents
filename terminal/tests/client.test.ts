import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ApiClient } from '../src/client/ApiClient.js';
import { AgentService } from '../src/client/AgentService.js';
import { ServerMonitor } from '../src/client/ServerMonitor.js';

// Mock fetch globally
const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

describe('ApiClient', () => {
  let client: ApiClient;

  beforeEach(() => {
    client = new ApiClient('http://localhost:8000');
    mockFetch.mockReset();
  });

  it('should construct with server URL', () => {
    expect(client.getServerUrl()).toBe('http://localhost:8000');
  });

  it('should reject invalid URLs', () => {
    client.setServerUrl('ftp://bad');
    expect(client.getServerUrl()).toBe('http://localhost:8000');
  });

  it('should accept valid HTTP URLs', () => {
    client.setServerUrl('http://other:9000');
    expect(client.getServerUrl()).toBe('http://other:9000');
  });

  describe('checkHealth', () => {
    it('should return true when server responds ok', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ status: 'ok' }),
      });
      expect(await client.checkHealth()).toBe(true);
    });

    it('should return false when server is down', async () => {
      mockFetch.mockRejectedValueOnce(new Error('ECONNREFUSED'));
      expect(await client.checkHealth()).toBe(false);
    });

    it('should return false when status is not ok', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ status: 'starting' }),
      });
      expect(await client.checkHealth()).toBe(false);
    });
  });

  describe('getAgents', () => {
    it('should return agent list from array response', async () => {
      const agents = [{ name: 'auto-pilot' }, { name: 'code-reviewer' }];
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(agents),
      });
      const result = await client.getAgents();
      expect(result).toEqual(agents);
    });

    it('should return agent list from object response', async () => {
      const agents = [{ name: 'auto-pilot' }];
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ agents }),
      });
      const result = await client.getAgents();
      expect(result).toEqual(agents);
    });

    it('should return empty array on error', async () => {
      mockFetch.mockRejectedValueOnce(new Error('fail'));
      expect(await client.getAgents()).toEqual([]);
    });
  });

  describe('streamChat', () => {
    it('should yield token events from SSE stream', async () => {
      const ssePayload = [
        'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n',
        'data: {"choices":[{"delta":{"content":" world"}}]}\n\n',
        'data: [DONE]\n\n',
      ].join('');

      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode(ssePayload));
          controller.close();
        },
      });

      mockFetch.mockResolvedValueOnce({
        ok: true,
        body: stream,
      });

      const events = [];
      for await (const event of client.streamChat('auto-pilot', [{ role: 'user', content: 'hi' }])) {
        events.push(event);
      }

      expect(events).toEqual([
        { type: 'token', content: 'Hello' },
        { type: 'token', content: ' world' },
        { type: 'done', fullContent: 'Hello world' },
      ]);
    });

    it('should yield error on server error', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        text: () => Promise.resolve('Internal Server Error'),
      });

      const events = [];
      for await (const event of client.streamChat('auto-pilot', [{ role: 'user', content: 'hi' }])) {
        events.push(event);
      }

      expect(events.length).toBe(1);
      expect(events[0].type).toBe('error');
    });
  });

  describe('cancelStream', () => {
    it('should not throw when no stream is active', () => {
      expect(() => client.cancelStream()).not.toThrow();
    });
  });
});

describe('AgentService', () => {
  let client: ApiClient;
  let service: AgentService;

  beforeEach(() => {
    client = new ApiClient('http://localhost:8000');
    service = new AgentService(client);
    mockFetch.mockReset();
  });

  it('should default to auto-pilot', () => {
    expect(service.currentAgent).toBe('auto-pilot');
  });

  it('should switch agents', () => {
    expect(service.setAgent('code-reviewer')).toBe(true);
    expect(service.currentAgent).toBe('code-reviewer');
  });

  it('should reject invalid agents when list is loaded', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve([{ name: 'auto-pilot' }, { name: 'code-reviewer' }]),
    });
    await service.refresh();
    expect(service.setAgent('nonexistent')).toBe(false);
    expect(service.currentAgent).toBe('auto-pilot');
  });

  it('should return agent names', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve([{ name: 'a' }, { name: 'b' }]),
    });
    await service.refresh();
    expect(service.getAgentNames()).toEqual(['a', 'b']);
  });
});

describe('ServerMonitor', () => {
  let client: ApiClient;
  let monitor: ServerMonitor;

  beforeEach(() => {
    client = new ApiClient('http://localhost:8000');
    monitor = new ServerMonitor(client);
    mockFetch.mockReset();
  });

  it('should start not alive', () => {
    expect(monitor.isAlive).toBe(false);
  });

  it('should report alive after successful health check', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ status: 'ok' }),
    });
    const alive = await monitor.waitForServer(2000);
    expect(alive).toBe(true);
    expect(monitor.isAlive).toBe(true);
  });

  it('should timeout when server never responds', async () => {
    mockFetch.mockRejectedValue(new Error('ECONNREFUSED'));
    const alive = await monitor.waitForServer(1000);
    expect(alive).toBe(false);
  });

  it('should clean up on dispose', () => {
    monitor.startPolling(100);
    monitor.dispose();
    // No assertions needed — just ensure no errors
  });
});
