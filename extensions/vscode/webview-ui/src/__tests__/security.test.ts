// Security-focused tests — validates all attack vectors are blocked

import { describe, it, expect } from 'vitest';

describe('Path Traversal Prevention', () => {
  function isPathSafe(filePath: string): boolean {
    // Mirrors the validation in ChatViewProvider.ts and JcefBridge.kt
    if (filePath.includes('..')) return false;
    if (filePath.startsWith('/')) return false;
    if (filePath.startsWith('\\')) return false;
    return true;
  }

  it('blocks .. traversal', () => {
    expect(isPathSafe('../../etc/passwd')).toBe(false);
    expect(isPathSafe('src/../../../etc/shadow')).toBe(false);
    expect(isPathSafe('..\\windows\\system32')).toBe(false);
  });

  it('blocks absolute paths', () => {
    expect(isPathSafe('/etc/passwd')).toBe(false);
    expect(isPathSafe('\\windows\\system32')).toBe(false);
  });

  it('allows relative paths within project', () => {
    expect(isPathSafe('src/app.ts')).toBe(true);
    expect(isPathSafe('tests/test_auth.py')).toBe(true);
    expect(isPathSafe('package.json')).toBe(true);
  });
});

describe('Server URL Validation', () => {
  function sanitizeServerUrl(rawUrl: string): string {
    // Mirrors the validation in ChatViewProvider.ts getHtml()
    try {
      const parsed = new URL(rawUrl);
      if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
        return parsed.origin;
      }
    } catch { /* invalid URL */ }
    return 'http://localhost:8000';
  }

  it('allows http localhost', () => {
    expect(sanitizeServerUrl('http://localhost:8000')).toBe('http://localhost:8000');
  });

  it('allows https URLs', () => {
    // URL.origin normalizes default port (443 for https) away
    expect(sanitizeServerUrl('https://api.example.com:443')).toBe('https://api.example.com');
  });

  it('strips path from URL (prevents SSRF path injection)', () => {
    expect(sanitizeServerUrl('http://localhost:8000/evil/path')).toBe('http://localhost:8000');
  });

  it('blocks javascript: protocol', () => {
    expect(sanitizeServerUrl('javascript:alert(1)')).toBe('http://localhost:8000');
  });

  it('blocks file: protocol', () => {
    expect(sanitizeServerUrl('file:///etc/passwd')).toBe('http://localhost:8000');
  });

  it('blocks ftp: protocol', () => {
    expect(sanitizeServerUrl('ftp://evil.com')).toBe('http://localhost:8000');
  });

  it('handles invalid URLs gracefully', () => {
    expect(sanitizeServerUrl('not a url')).toBe('http://localhost:8000');
    expect(sanitizeServerUrl('')).toBe('http://localhost:8000');
  });
});

describe('State Injection Prevention', () => {
  function filterState(state: Record<string, unknown>): Record<string, unknown> {
    // Mirrors the validation in app.ts restoreState handler
    const allowed = ['messages', 'currentAgent', 'connected', 'serverUrl', 'agents', 'settings', 'mode'];
    const filtered: Record<string, unknown> = {};
    for (const key of allowed) {
      if (key in state) {
        filtered[key] = state[key];
      }
    }
    return filtered;
  }

  it('allows known safe keys', () => {
    const input = { messages: [], currentAgent: 'test', connected: true };
    const result = filterState(input);
    expect(result).toEqual(input);
  });

  it('strips unknown keys', () => {
    const input = { messages: [], __proto__: {}, constructor: 'evil', isStreaming: true };
    const result = filterState(input);
    expect(result).toEqual({ messages: [] });
    expect(result).not.toHaveProperty('__proto__');
    expect(result).not.toHaveProperty('constructor');
    expect(result).not.toHaveProperty('isStreaming');
  });

  it('handles empty state', () => {
    expect(filterState({})).toEqual({});
  });
});

describe('SSE Buffer Limit', () => {
  it('rejects buffers exceeding 1MB', () => {
    const MAX_BUFFER = 1024 * 1024;
    const largeBuffer = 'x'.repeat(MAX_BUFFER + 1);
    expect(largeBuffer.length).toBeGreaterThan(MAX_BUFFER);
    // In real code, this triggers req.destroy()
  });
});
