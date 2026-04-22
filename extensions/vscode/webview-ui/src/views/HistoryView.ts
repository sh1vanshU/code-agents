// Code Agents — History View

import { store, type SessionInfo } from '../state';
import { loadHistory, resumeSession, exportChat } from '../api';

export class HistoryView {
  private el: HTMLElement;
  private sessions: SessionInfo[] = [];

  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'overlay overlay-enter';
    this.el.style.display = 'none';

    store.subscribe((state) => {
      if (state.view === 'history') {
        this.el.style.display = '';
        loadHistory();
      } else {
        this.el.style.display = 'none';
      }
    });
  }

  mount(parent: HTMLElement): void {
    parent.appendChild(this.el);
  }

  /** Called from app.ts when history data arrives from host */
  setSessions(sessions: SessionInfo[]): void {
    this.sessions = sessions;
    this.render();
  }

  private render(): void {
    const groups = this.groupByDate(this.sessions);

    let historyHtml = '';
    if (this.sessions.length === 0) {
      historyHtml = `<div class="history-empty">No saved conversations yet.</div>`;
    } else {
      for (const [label, items] of Object.entries(groups)) {
        historyHtml += `<div class="history-group-label">${label}</div>`;
        for (const item of items) {
          const time = new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          historyHtml += `
            <div class="history-item" data-session-id="${item.id}" data-agent="${item.agent}">
              <div class="history-item-content">
                <div class="history-item-title">${this.escapeHtml(item.title)}</div>
                <div class="history-item-meta">${item.messageCount} messages &bull; ${time}</div>
              </div>
              <span class="history-item-agent">${item.agent}</span>
              <button class="btn-icon history-item-delete" title="Delete" data-session-id="${item.id}">&times;</button>
            </div>
          `;
        }
      }
    }

    this.el.innerHTML = `
      <div class="overlay-header">
        <button class="btn-back" id="history-back">&larr; Back</button>
        <span class="overlay-title">Chat History</span>
      </div>
      <div class="overlay-body">
        <div class="history-search">
          <input class="input" id="history-search-input" placeholder="Search conversations...">
        </div>
        <div id="history-list">${historyHtml}</div>
      </div>
      <div class="history-footer">
        <button class="btn" id="history-export">Export All</button>
      </div>
    `;

    this.bindEvents();
  }

  private bindEvents(): void {
    // Back
    this.el.querySelector('#history-back')?.addEventListener('click', () => {
      store.update({ view: 'chat' });
    });

    // Click session to resume — use event delegation on list container
    const historyList = this.el.querySelector('#history-list');
    if (historyList) {
      historyList.addEventListener('click', (e) => {
        const target = e.target as HTMLElement;
        if (target.classList.contains('history-item-delete')) return;
        const item = target.closest('.history-item') as HTMLElement | null;
        if (item?.dataset.sessionId) {
          resumeSession(item.dataset.sessionId);
          store.update({ view: 'chat' });
        }
      });
    }

    // Search filter
    this.el.querySelector('#history-search-input')?.addEventListener('input', (e) => {
      const query = (e.target as HTMLInputElement).value.toLowerCase();
      this.el.querySelectorAll('.history-item').forEach(item => {
        const title = item.querySelector('.history-item-title')?.textContent?.toLowerCase() || '';
        const agent = (item as HTMLElement).dataset.agent?.toLowerCase() || '';
        (item as HTMLElement).style.display = (title.includes(query) || agent.includes(query)) ? '' : 'none';
      });
    });

    // Export
    this.el.querySelector('#history-export')?.addEventListener('click', () => {
      exportChat('markdown');
    });
  }

  private groupByDate(sessions: SessionInfo[]): Record<string, SessionInfo[]> {
    const groups: Record<string, SessionInfo[]> = {};
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const yesterday = today - 86400000;

    for (const s of sessions) {
      let label: string;
      if (s.timestamp >= today) label = 'Today';
      else if (s.timestamp >= yesterday) label = 'Yesterday';
      else label = new Date(s.timestamp).toLocaleDateString();

      if (!groups[label]) groups[label] = [];
      groups[label].push(s);
    }
    return groups;
  }

  private escapeHtml(text: string): string {
    const el = document.createElement('span');
    el.textContent = text;
    return el.innerHTML;
  }

  getElement(): HTMLElement {
    return this.el;
  }
}
