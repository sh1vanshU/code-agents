// Code Agents — Message Bubble Component

import { type Message } from '../state';
import { renderMarkdown, escapeHtml } from '../markdown/renderer';
import { applyDiff, openFile } from '../api';

export class MessageBubble {
  private el: HTMLElement;

  constructor(private message: Message) {
    this.el = document.createElement('div');
    this.el.className = `message ${message.role} animate-in`;

    if (message.agent) {
      this.el.dataset.agent = message.agent;
    }

    this.render();
  }

  private render(): void {
    const msg = this.message;

    if (msg.role === 'error') {
      this.el.innerHTML = escapeHtml(msg.content);
      return;
    }

    if (msg.role === 'system') {
      this.el.innerHTML = escapeHtml(msg.content);
      return;
    }

    let html = '';

    // Header (for assistant messages)
    if (msg.role === 'assistant' && msg.agent) {
      const time = new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      html += `<div class="message-header">
        <span class="message-sender">${escapeHtml(msg.agent)}</span>
        <span class="message-time">${time}</span>
      </div>`;
    }

    // User message header with time
    if (msg.role === 'user') {
      const time = new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      html += `<div class="message-header">
        <span class="message-sender" style="color:var(--ca-text-secondary)">You</span>
        <span class="message-time">${time}</span>
      </div>`;
    }

    // File context chip
    if (msg.filePath) {
      const label = msg.fileLines ? `${msg.filePath} (${msg.fileLines})` : msg.filePath;
      html += `<div class="file-chip" data-path="${escapeHtml(msg.filePath)}">
        <span class="file-icon">📄</span>
        <span>${escapeHtml(label)}</span>
      </div>`;
    }

    // Content
    html += `<div class="message-content">`;
    if (msg.role === 'user') {
      html += escapeHtml(msg.content).replace(/\n/g, '<br>');
    } else {
      html += renderMarkdown(msg.content);
    }
    html += `</div>`;

    // Footer (for assistant messages)
    if (msg.role === 'assistant' && msg.content) {
      html += `<div class="message-footer">
        <button class="btn-icon btn-reaction" data-reaction="up" title="Helpful">👍</button>
        <button class="btn-icon btn-reaction" data-reaction="down" title="Not helpful">👎</button>
        <button class="btn-icon btn-retry" title="Retry">↻</button>
        <button class="btn-icon btn-copy-msg" title="Copy message">📋</button>
        <button class="btn-icon btn-delegate" title="Delegate to another agent">→</button>
      </div>`;
    }

    this.el.innerHTML = html;
    this.bindEvents();
  }

  private bindEvents(): void {
    // File chip click — open file
    this.el.querySelectorAll('.file-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const path = (chip as HTMLElement).dataset.path;
        if (path) openFile(path);
      });
    });

    // Copy code button
    this.el.querySelectorAll('.btn-copy').forEach(btn => {
      btn.addEventListener('click', () => {
        const code = (btn as HTMLElement).dataset.code || '';
        navigator.clipboard.writeText(decodeAttr(code));
        (btn as HTMLElement).textContent = '✓';
        setTimeout(() => { if ((btn as HTMLElement).isConnected) (btn as HTMLElement).textContent = '📋'; }, 1500);
      });
    });

    // Apply code button
    this.el.querySelectorAll('.btn-apply').forEach(btn => {
      btn.addEventListener('click', () => {
        const code = (btn as HTMLElement).dataset.code || '';
        applyDiff('', decodeAttr(code));
        (btn as HTMLElement).textContent = '✓ Applied';
      });
    });

    // Apply diff button
    this.el.querySelectorAll('.btn-apply-diff').forEach(btn => {
      btn.addEventListener('click', () => {
        const file = (btn as HTMLElement).dataset.file || '';
        const diff = (btn as HTMLElement).dataset.diff || '';
        applyDiff(file, decodeAttr(diff));
        (btn as HTMLElement).textContent = '✓ Applied';
        (btn as HTMLElement).classList.add('btn-ghost');
        (btn as HTMLElement).setAttribute('disabled', '');
      });
    });

    // Copy message
    this.el.querySelectorAll('.btn-copy-msg').forEach(btn => {
      btn.addEventListener('click', () => {
        navigator.clipboard.writeText(this.message.content);
        (btn as HTMLElement).textContent = '✓';
        setTimeout(() => { if ((btn as HTMLElement).isConnected) (btn as HTMLElement).textContent = '📋'; }, 1500);
      });
    });
  }

  getElement(): HTMLElement {
    return this.el;
  }
}

function decodeAttr(text: string): string {
  return text
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>');
}
