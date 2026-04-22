// Code Agents — Toolbar Component

import { store, type ModeState } from '../state';
import { changeAgent, changeMode } from '../api';

const AGENT_GROUPS: Record<string, string[]> = {
  Orchestration: ['auto-pilot'],
  Code: ['code-writer', 'code-reviewer', 'code-reasoning', 'code-tester'],
  Testing: ['test-coverage', 'qa-regression'],
  DevOps: ['jenkins-cicd', 'argocd-verify', 'git-ops'],
  'Data & Ops': ['jira-ops', 'redash-query', 'security'],
};

export class Toolbar {
  private el: HTMLElement;

  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'toolbar';
    this.render();

    store.subscribe(() => this.updateStatus());
  }

  mount(parent: HTMLElement): void {
    parent.appendChild(this.el);
  }

  private render(): void {
    const state = store.getState();
    this.el.innerHTML = `
      <div class="toolbar-left">
        <div class="mode-selector">
          <button class="mode-tab ${state.mode === 'chat' ? 'active' : ''}" data-mode="chat">Chat</button>
          <button class="mode-tab ${state.mode === 'plan' ? 'active' : ''}" data-mode="plan">Plan</button>
          <button class="mode-tab ${state.mode === 'agent' ? 'active' : ''}" data-mode="agent">Agent</button>
        </div>
        <div class="agent-select-wrapper" data-agent="${state.currentAgent}">
          <span class="agent-dot"></span>
          <select class="select agent-selector" title="Select agent">
            ${this.renderAgentOptions(state.currentAgent)}
          </select>
        </div>
      </div>
      <div class="toolbar-right">
        <span class="status-dot ${state.connected ? 'connected' : 'disconnected'}"
              title="${state.connected ? 'Server connected' : 'Server disconnected'}"></span>
        <button class="btn-icon btn-history" title="Chat history">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
        </button>
        <button class="btn-icon btn-settings-toggle" title="Settings">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        </button>
        <button class="btn-icon btn-new-chat" title="New chat">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        </button>
      </div>
    `;

    this.bindEvents();
  }

  private renderAgentOptions(currentAgent: string): string {
    const state = store.getState();
    return state.agents.map(a =>
      `<option value="${a.name}" ${a.name === currentAgent ? 'selected' : ''}>${a.name}</option>`
    ).join('');
  }

  private bindEvents(): void {
    // Use event delegation on the toolbar root to prevent listener accumulation on re-render
    this.el.onclick = (e) => {
      const target = e.target as HTMLElement;

      // Mode tabs
      const modeTab = target.closest('.mode-tab') as HTMLElement | null;
      if (modeTab?.dataset.mode) {
        const mode = modeTab.dataset.mode as ModeState;
        store.update({ mode });
        changeMode(mode);
        // Update active tab without full re-render
        this.el.querySelectorAll('.mode-tab').forEach(t => t.classList.toggle('active', t === modeTab));
        return;
      }

      // Settings button
      if (target.closest('.btn-settings-toggle')) {
        store.update({ view: 'settings' });
        return;
      }

      // History button
      if (target.closest('.btn-history')) {
        store.update({ view: 'history' });
        return;
      }

      // New chat button
      if (target.closest('.btn-new-chat')) {
        store.clearMessages();
        store.update({ view: 'chat' });
        return;
      }
    };

    // Agent selector (onchange, not onclick — separate handler)
    const agentSelect = this.el.querySelector('.agent-selector') as HTMLSelectElement;
    if (agentSelect) {
      agentSelect.onchange = () => {
        const agent = agentSelect.value;
        store.update({ currentAgent: agent });
        changeAgent(agent);
        const wrapper = this.el.querySelector('.agent-select-wrapper') as HTMLElement;
        if (wrapper) wrapper.dataset.agent = agent;
      };
    }
  }

  private updateStatus(): void {
    const state = store.getState();
    const dot = this.el.querySelector('.status-dot');
    if (dot) {
      dot.className = `status-dot ${state.connected ? 'connected' : 'disconnected'}`;
      dot.setAttribute('title', state.connected ? 'Server connected' : 'Server disconnected');
    }
  }
}
