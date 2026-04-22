// Code Agents — Markdown to HTML Renderer (zero dependencies)

import { highlight } from './highlighter';

export function escapeHtml(text: string): string {
  const el = document.createElement('span');
  el.textContent = text;
  return el.innerHTML;
}

export function renderMarkdown(text: string): string {
  if (!text) return '';

  let html = escapeHtml(text);

  // Fenced code blocks: ```lang\n...\n``` (allows trailing spaces after lang)
  html = html.replace(/```(\w*)\s*\n([\s\S]*?)\n```/g, (_, lang: string, code: string) => {
    const langLabel = lang || 'code';
    const langClass = lang ? ` class="language-${lang}"` : '';
    return `<div class="code-block-wrapper">
      <div class="code-block-header">
        <span class="code-block-lang">${escapeHtml(langLabel)}</span>
        <div class="code-block-actions">
          <button class="btn-icon btn-copy" data-code="${escapeAttr(code)}" title="Copy">📋</button>
          <button class="btn-icon btn-apply" data-code="${escapeAttr(code)}" title="Apply to editor">✓</button>
        </div>
      </div>
      <div class="code-block-content"><code${langClass}>${lang ? highlight(code, lang) : code}</code></div>
    </div>`;
  });

  // Inline code: `code`
  html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');

  // Bold: **text**
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

  // Italic: *text*
  html = html.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>');

  // Headings
  html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^# (.+)$/gm, '<h3 style="font-size:16px">$1</h3>');

  // Blockquotes — group consecutive `> ` lines into single blockquote
  html = html.replace(/(?:^&gt; (.+)$\n?)+/gm, (match) => {
    const lines = match.trim().split('\n')
      .map(line => line.replace(/^&gt; /, ''))
      .join('<br>');
    return `<blockquote>${lines}</blockquote>`;
  });

  // Unordered lists — group consecutive `- ` lines
  html = html.replace(/(?:^- (.+)$\n?)+/gm, (match) => {
    const items = match.trim().split('\n')
      .map((line) => `<li>${line.replace(/^- /, '')}</li>`)
      .join('');
    return `<ul>${items}</ul>`;
  });

  // Ordered lists — group consecutive `N. ` lines
  html = html.replace(/(?:^\d+\. (.+)$\n?)+/gm, (match) => {
    const items = match.trim().split('\n')
      .map((line) => `<li>${line.replace(/^\d+\. /, '')}</li>`)
      .join('');
    return `<ol>${items}</ol>`;
  });

  // Links: [text](url) — validate URLs to prevent javascript: XSS
  html = html.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    (_, linkText: string, url: string) => {
      const trimmedUrl = url.trim();
      if (trimmedUrl.startsWith('javascript:') || trimmedUrl.startsWith('data:') || trimmedUrl.startsWith('vbscript:')) {
        return linkText;
      }
      return `<a href="${escapeAttr(trimmedUrl)}" target="_blank" rel="noopener">${linkText}</a>`;
    }
  );

  // Horizontal rule
  html = html.replace(/^---$/gm, '<hr class="md-hr">');

  // Line breaks (preserve newlines outside of blocks)
  html = html.replace(/\n/g, '<br>');

  // Clean up excess <br> around block elements
  html = html.replace(/<br>\s*(<(?:div|pre|ul|ol|h[34]|blockquote|hr))/g, '$1');
  html = html.replace(/(<\/(?:div|pre|ul|ol|h[34]|blockquote)>)\s*<br>/g, '$1');

  return html;
}

/** Render diff-specific content with colored lines */
export function renderDiff(text: string, filePath?: string): string {
  const lines = text.split('\n');
  const rendered = lines.map((line) => {
    if (line.startsWith('+') && !line.startsWith('+++')) {
      return `<div class="diff-line-add">${escapeHtml(line)}</div>`;
    } else if (line.startsWith('-') && !line.startsWith('---')) {
      return `<div class="diff-line-remove">${escapeHtml(line)}</div>`;
    } else if (line.startsWith('@@')) {
      return `<div class="diff-line-context" style="color:var(--ca-accent)">${escapeHtml(line)}</div>`;
    }
    return `<div class="diff-line-context">${escapeHtml(line)}</div>`;
  }).join('');

  const header = filePath ? escapeHtml(filePath) : 'Diff';
  return `<div class="diff-block">
    <div class="diff-header">
      <span>${header}</span>
    </div>
    <div class="diff-content">${rendered}</div>
    <div class="diff-actions">
      <button class="btn btn-success btn-sm btn-apply-diff" data-file="${escapeAttr(filePath || '')}" data-diff="${escapeAttr(text)}">✓ Accept</button>
      <button class="btn btn-danger btn-sm btn-reject-diff">✗ Reject</button>
    </div>
  </div>`;
}

function escapeAttr(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
