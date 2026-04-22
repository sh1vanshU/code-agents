import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock fetch globally
const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

// Mock child_process
vi.mock('node:child_process', () => ({
  execSync: vi.fn().mockReturnValue('mocked output'),
  spawn: vi.fn().mockReturnValue({
    unref: vi.fn(),
    pid: 12345,
  }),
}));

describe('CLI Commands', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  describe('Start command', () => {
    it('should export a default Command class', async () => {
      const mod = await import('../src/commands/start.js');
      expect(mod.default).toBeDefined();
      expect(mod.default.description).toContain('Start');
    });

    it('should have correct flags', async () => {
      const mod = await import('../src/commands/start.js');
      expect(mod.default.flags).toHaveProperty('server');
      expect(mod.default.flags).toHaveProperty('dir');
      expect(mod.default.flags).toHaveProperty('timeout');
    });
  });

  describe('Stop command', () => {
    it('should export a default Command class', async () => {
      const mod = await import('../src/commands/stop.js');
      expect(mod.default).toBeDefined();
      expect(mod.default.description).toContain('Stop');
    });

    it('should have port flag', async () => {
      const mod = await import('../src/commands/stop.js');
      expect(mod.default.flags).toHaveProperty('port');
    });
  });

  describe('Status command', () => {
    it('should export a default Command class', async () => {
      const mod = await import('../src/commands/status.js');
      expect(mod.default).toBeDefined();
      expect(mod.default.description).toContain('health');
    });

    it('should have server flag', async () => {
      const mod = await import('../src/commands/status.js');
      expect(mod.default.flags).toHaveProperty('server');
    });
  });

  describe('Agents command', () => {
    it('should export a default Command class', async () => {
      const mod = await import('../src/commands/agents.js');
      expect(mod.default).toBeDefined();
      expect(mod.default.description).toContain('agent');
    });
  });

  describe('Doctor command', () => {
    it('should export a default Command class', async () => {
      const mod = await import('../src/commands/doctor.js');
      expect(mod.default).toBeDefined();
      expect(mod.default.description).toContain('diagnostic');
    });
  });

  describe('Init command', () => {
    it('should export a default Command class', async () => {
      const mod = await import('../src/commands/init.js');
      expect(mod.default).toBeDefined();
      expect(mod.default.description).toContain('Initialize');
    });

    it('should have dir flag', async () => {
      const mod = await import('../src/commands/init.js');
      expect(mod.default.flags).toHaveProperty('dir');
    });
  });
});
