import { describe, it, expect } from 'vitest';

describe('TUI Components', () => {
  it('should import StatusBar', async () => {
    const mod = await import('../src/tui/StatusBar.js');
    expect(mod.StatusBar).toBeDefined();
  });

  it('should import ThinkingIndicator', async () => {
    const mod = await import('../src/tui/ThinkingIndicator.js');
    expect(mod.ThinkingIndicator).toBeDefined();
  });

  it('should import DiffView and parseDiff', async () => {
    const mod = await import('../src/tui/DiffView.js');
    expect(mod.DiffView).toBeDefined();
    expect(mod.parseDiff).toBeDefined();
  });

  it('should parse unified diff', async () => {
    const { parseDiff } = await import('../src/tui/DiffView.js');
    const lines = parseDiff('+added line\n-removed line\n context line');
    expect(lines).toHaveLength(3);
    expect(lines[0].type).toBe('add');
    expect(lines[1].type).toBe('remove');
    expect(lines[2].type).toBe('context');
  });

  it('should import FileTree', async () => {
    const mod = await import('../src/tui/FileTree.js');
    expect(mod.FileTree).toBeDefined();
  });

  it('should import ProgressDashboard', async () => {
    const mod = await import('../src/tui/ProgressDashboard.js');
    expect(mod.ProgressDashboard).toBeDefined();
  });

  it('should import TokenBudgetBar', async () => {
    const mod = await import('../src/tui/TokenBudgetBar.js');
    expect(mod.TokenBudgetBar).toBeDefined();
  });

  it('should import FullScreenApp', async () => {
    const mod = await import('../src/tui/FullScreenApp.js');
    expect(mod.FullScreenApp).toBeDefined();
  });
});
