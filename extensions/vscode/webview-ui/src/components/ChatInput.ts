// Code Agents — Chat Input Component

import { store, type AppState } from '../state';
import { sendChatMessage, cancelStream, sendSlashCommand } from '../api';
import { SLASH_COMMANDS } from './SlashPalette';
import { escapeHtml } from '../markdown/renderer';

export class ChatInput {
  private el: HTMLElement;
  private textarea!: HTMLTextAreaElement;
  private sendBtn!: HTMLButtonElement;

  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'input-area';
    this.render();

    store.subscribe((state) => this.onStateChange(state));
  }

  mount(parent: HTMLElement): void {
    parent.appendChild(this.el);
  }

  focus(): void {
    this.textarea?.focus();
  }

  setText(text: string): void {
    if (this.textarea) {
      this.textarea.value = text;
      this.autoResize();
    }
  }

  private render(): void {
    const state = store.getState();

    this.el.innerHTML = `
      <div class="input-context" id="input-context"></div>
      <div class="input-toolbar">
        <button class="btn-icon btn-mention" title="Mention file or agent (@)">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-3.92 7.94"/></svg>
        </button>
        <button class="btn-icon btn-attach" title="Attach file context">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
        </button>
        <span class="slash-indicator" id="slash-trigger" title="Slash commands">/commands</span>
      </div>
      <div class="input-row" style="position:relative">
        <div id="slash-palette-mount"></div>
        <div id="mention-picker-mount"></div>
        <textarea
          class="chat-textarea"
          id="chat-textarea"
          placeholder="Ask anything... (Enter to send, Shift+Enter for newline)"
          rows="1"
          ${state.isStreaming ? 'disabled' : ''}
        ></textarea>
        <button class="btn-send ${state.isStreaming ? 'stop' : ''}" id="btn-send"
                title="${state.isStreaming ? 'Stop generation' : 'Send message'}">
          ${state.isStreaming
            ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>'
            : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13"/><path d="M22 2L15 22L11 13L2 9L22 2Z"/></svg>'
          }
        </button>
      </div>
      <div class="input-hint">
        <span>Enter to send, Shift+Enter for newline</span>
        <span class="token-counter" id="token-counter"></span>
      </div>
    `;

    this.textarea = this.el.querySelector('#chat-textarea') as HTMLTextAreaElement;
    this.sendBtn = this.el.querySelector('#btn-send') as HTMLButtonElement;

    this.bindEvents();
    this.renderContext();
  }

  private bindEvents(): void {
    // Send / Stop
    this.sendBtn.addEventListener('click', () => {
      if (store.getState().isStreaming) {
        cancelStream();
      } else {
        this.handleSend();
      }
    });

    // Textarea keydown
    this.textarea.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.handleSend();
      }

      // Slash palette trigger
      if (e.key === '/' && this.textarea.value === '') {
        store.update({ showSlashPalette: true, slashFilter: '' });
      }

      // Mention trigger
      if (e.key === '@') {
        store.update({ showMentionPicker: true, mentionFilter: '' });
      }

      // Escape closes palettes
      if (e.key === 'Escape') {
        store.update({ showSlashPalette: false, showMentionPicker: false });
      }
    });

    // Auto-resize
    this.textarea.addEventListener('input', () => {
      this.autoResize();

      // Update slash filter
      if (store.getState().showSlashPalette) {
        const val = this.textarea.value;
        if (val.startsWith('/')) {
          store.update({ slashFilter: val.slice(1) });
        } else {
          store.update({ showSlashPalette: false });
        }
      }

      // Update mention filter
      if (store.getState().showMentionPicker) {
        const val = this.textarea.value;
        const atIdx = val.lastIndexOf('@');
        if (atIdx >= 0) {
          store.update({ mentionFilter: val.slice(atIdx + 1) });
        } else {
          store.update({ showMentionPicker: false });
        }
      }
    });

    // Slash trigger click
    this.el.querySelector('#slash-trigger')?.addEventListener('click', () => {
      store.update({ showSlashPalette: !store.getState().showSlashPalette });
      this.textarea.focus();
    });

    // Mention button
    this.el.querySelector('.btn-mention')?.addEventListener('click', () => {
      // Insert @ at cursor position, not at end
      const start = this.textarea.selectionStart;
      const end = this.textarea.selectionEnd;
      const text = this.textarea.value;
      this.textarea.value = text.slice(0, start) + '@' + text.slice(end);
      this.textarea.selectionStart = this.textarea.selectionEnd = start + 1;
      this.textarea.focus();
      store.update({ showMentionPicker: true, mentionFilter: '' });
    });
  }

  private handleSend(): void {
    const text = this.textarea.value.trim();
    if (!text || store.getState().isStreaming) return;

    // Check for slash command
    if (text.startsWith('/')) {
      const parts = text.split(' ');
      const cmd = parts[0].slice(1);
      const args = parts.slice(1).join(' ');
      const found = SLASH_COMMANDS.find(c => c.command === cmd);
      if (found) {
        sendSlashCommand(cmd, args);
        this.textarea.value = '';
        this.autoResize();
        store.update({ showSlashPalette: false });
        return;
      }
    }

    // Build context prefix
    const state = store.getState();
    let fullText = text;
    if (state.contextFiles.length > 0) {
      const ctx = state.contextFiles.map(f =>
        f.lines ? `File: ${f.path} (${f.lines})` : `File: ${f.path}`
      ).join('\n');
      fullText = `${ctx}\n\n${text}`;
    }

    // Add user message to state
    store.addMessage({
      id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
      role: 'user',
      content: text,
      timestamp: Date.now(),
      filePath: state.contextFiles[0]?.path,
      fileLines: state.contextFiles[0]?.lines,
    });

    // Clear input and context
    this.textarea.value = '';
    this.autoResize();
    store.update({ contextFiles: [], showSlashPalette: false, showMentionPicker: false });

    // Send to IDE host
    sendChatMessage(fullText, state.currentAgent);
  }

  private autoResize(): void {
    this.textarea.style.height = '0';
    // scrollHeight includes padding but not border — add 2px for border
    this.textarea.style.height = Math.min(this.textarea.scrollHeight + 2, 150) + 'px';
  }

  private renderContext(): void {
    const ctx = this.el.querySelector('#input-context') as HTMLElement;
    if (!ctx) return;

    const state = store.getState();
    if (state.contextFiles.length === 0) {
      ctx.style.display = 'none';
      return;
    }

    ctx.style.display = 'flex';
    ctx.innerHTML = state.contextFiles.map(f => `
      <div class="file-chip">
        <span class="file-icon">📄</span>
        <span>${escapeHtml(f.lines ? `${f.path} (${f.lines})` : f.path)}</span>
        <span class="btn-remove" data-path="${escapeHtml(f.path)}">&times;</span>
      </div>
    `).join('');

    // Use event delegation on parent to avoid listener accumulation
    ctx.onclick = (e) => {
      const target = (e.target as HTMLElement).closest('.btn-remove') as HTMLElement | null;
      if (target?.dataset.path) {
        store.removeContextFile(target.dataset.path);
        this.renderContext();
      }
    };
  }

  private onStateChange(state: AppState): void {
    // Update send/stop button
    if (this.sendBtn) {
      this.sendBtn.className = `btn-send ${state.isStreaming ? 'stop' : ''}`;
      this.sendBtn.title = state.isStreaming ? 'Stop generation' : 'Send message';
      this.sendBtn.innerHTML = state.isStreaming
        ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>'
        : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13"/><path d="M22 2L15 22L11 13L2 9L22 2Z"/></svg>';
    }

    // Toggle textarea disabled
    if (this.textarea) {
      this.textarea.disabled = state.isStreaming;
      if (!state.isStreaming) this.textarea.focus();
    }

    // Update context chips
    this.renderContext();

    // Token counter
    const counter = this.el.querySelector('#token-counter');
    if (counter && state.sessionTokens > 0) {
      counter.textContent = `${state.sessionTokens.toLocaleString()} tokens`;
    }
  }

  getElement(): HTMLElement {
    return this.el;
  }
}
