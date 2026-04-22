// Tests for the markdown renderer — security + correctness

import { describe, it, expect, beforeAll } from 'vitest';
import { JSDOM } from 'jsdom';

// Set up DOM for escapeHtml
let escapeHtml: (text: string) => string;
let renderMarkdown: (text: string) => string;

beforeAll(async () => {
  const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>');
  global.document = dom.window.document as any;

  // Dynamic import after DOM is ready
  const mod = await import('../markdown/renderer');
  escapeHtml = mod.escapeHtml;
  renderMarkdown = mod.renderMarkdown;
});

describe('escapeHtml', () => {
  it('escapes HTML entities', () => {
    expect(escapeHtml('<script>alert("xss")</script>')).toBe(
      '&lt;script&gt;alert("xss")&lt;/script&gt;'
    );
  });

  it('escapes ampersands', () => {
    expect(escapeHtml('a & b')).toBe('a &amp; b');
  });

  it('handles empty string', () => {
    expect(escapeHtml('')).toBe('');
  });
});

describe('renderMarkdown', () => {
  it('returns empty for empty input', () => {
    expect(renderMarkdown('')).toBe('');
  });

  it('renders bold text', () => {
    const html = renderMarkdown('This is **bold** text');
    expect(html).toContain('<strong>bold</strong>');
  });

  it('renders italic text', () => {
    const html = renderMarkdown('This is *italic* text');
    expect(html).toContain('<em>italic</em>');
  });

  it('renders inline code', () => {
    const html = renderMarkdown('Use `npm install` to install');
    expect(html).toContain('<code>npm install</code>');
  });

  it('renders headings', () => {
    const html = renderMarkdown('## Section Title');
    expect(html).toContain('<h3>Section Title</h3>');
  });

  it('renders unordered lists', () => {
    const html = renderMarkdown('- item 1\n- item 2');
    expect(html).toContain('<ul>');
    expect(html).toContain('<li>item 1</li>');
    expect(html).toContain('<li>item 2</li>');
  });

  it('renders fenced code blocks with language', () => {
    const html = renderMarkdown('```python\nprint("hello")\n```');
    expect(html).toContain('code-block-wrapper');
    expect(html).toContain('python');
    expect(html).toContain('print');
  });

  it('renders code blocks with copy button', () => {
    const html = renderMarkdown('```js\nconst x = 1;\n```');
    expect(html).toContain('btn-copy');
    expect(html).toContain('btn-apply');
  });

  // Security tests
  it('blocks javascript: URLs in links', () => {
    const html = renderMarkdown('[click me](javascript:alert(1))');
    expect(html).not.toContain('href="javascript');
    expect(html).toContain('click me'); // text preserved
  });

  it('blocks data: URLs in links', () => {
    const html = renderMarkdown('[click](data:text/html,<script>alert(1)</script>)');
    expect(html).not.toContain('href="data:');
  });

  it('blocks vbscript: URLs in links', () => {
    const html = renderMarkdown('[click](vbscript:msgbox("xss"))');
    expect(html).not.toContain('href="vbscript');
  });

  it('allows safe http URLs in links', () => {
    const html = renderMarkdown('[docs](https://example.com/docs)');
    expect(html).toContain('href="https://example.com/docs"');
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener"');
  });

  it('escapes HTML in input before processing markdown', () => {
    const html = renderMarkdown('<img src=x onerror=alert(1)>');
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img');
  });

  it('renders blockquotes', () => {
    const html = renderMarkdown('> This is a quote');
    expect(html).toContain('<blockquote>');
  });

  it('renders horizontal rules', () => {
    const html = renderMarkdown('---');
    expect(html).toContain('<hr');
  });
});
