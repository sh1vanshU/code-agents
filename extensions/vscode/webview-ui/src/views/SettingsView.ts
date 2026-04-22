// Code Agents — Settings View

import { store } from '../state';
import { saveSettings } from '../api';

export class SettingsView {
  private el: HTMLElement;

  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'overlay overlay-enter';
    this.el.style.display = 'none';

    store.subscribe((state) => {
      if (state.view === 'settings') {
        this.render();
        this.el.style.display = '';
      } else {
        this.el.style.display = 'none';
      }
    });
  }

  mount(parent: HTMLElement): void {
    parent.appendChild(this.el);
  }

  private render(): void {
    const state = store.getState();
    const s = state.settings;

    this.el.innerHTML = `
      <div class="overlay-header">
        <button class="btn-back" id="settings-back">&larr; Back</button>
        <span class="overlay-title">Settings</span>
      </div>
      <div class="overlay-body">

        <div class="settings-section">
          <div class="settings-section-title">Connection</div>
          <div class="settings-card">
            <div class="settings-row">
              <span class="settings-label">Server URL</span>
              <div class="settings-value">
                <input class="input" id="set-server-url" value="${state.serverUrl}" style="max-width:200px;text-align:right">
              </div>
            </div>
            <div class="settings-row">
              <span class="settings-label">Status</span>
              <div class="settings-value flex items-center gap-4" style="justify-content:flex-end">
                <span class="status-dot ${state.connected ? 'connected' : 'disconnected'}"></span>
                <span style="font-size:var(--ca-font-size-sm)">${state.connected ? 'Connected' : 'Disconnected'}</span>
              </div>
            </div>
            <div class="settings-row">
              <span class="settings-label">Auto-start server</span>
              <div class="settings-value">
                <button class="toggle ${s.autoStartServer ? 'on' : ''}" id="set-autostart"></button>
              </div>
            </div>
          </div>
        </div>

        <div class="settings-section">
          <div class="settings-section-title">Defaults</div>
          <div class="settings-card">
            <div class="settings-row">
              <span class="settings-label">Agent</span>
              <div class="settings-value">
                <select class="select" id="set-agent" style="max-width:160px;margin-left:auto">
                  ${state.agents.map(a => `<option value="${a.name}" ${a.name === state.currentAgent ? 'selected' : ''}>${a.name}</option>`).join('')}
                </select>
              </div>
            </div>
            <div class="settings-row">
              <span class="settings-label">Context window</span>
              <div class="settings-value">
                <input class="input" id="set-context-window" type="number" min="1" max="20" value="${s.contextWindow}" style="max-width:80px;text-align:right">
              </div>
            </div>
          </div>
        </div>

        <div class="settings-section">
          <div class="settings-section-title">Behavior</div>
          <div class="settings-card">
            <div class="settings-row">
              <span class="settings-label">Auto-run commands</span>
              <div class="settings-value">
                <button class="toggle ${s.autoRun ? 'on' : ''}" id="set-autorun"></button>
              </div>
            </div>
            <div class="settings-row">
              <span class="settings-label">Require confirmation</span>
              <div class="settings-value">
                <button class="toggle ${s.requireConfirm ? 'on' : ''}" id="set-confirm"></button>
              </div>
            </div>
            <div class="settings-row">
              <span class="settings-label">Dry-run mode</span>
              <div class="settings-value">
                <button class="toggle ${s.dryRun ? 'on' : ''}" id="set-dryrun"></button>
              </div>
            </div>
            <div class="settings-row">
              <span class="settings-label">Superpower</span>
              <div class="settings-value">
                <button class="toggle ${s.superpower ? 'on' : ''}" id="set-superpower"></button>
              </div>
            </div>
          </div>
        </div>

        <div class="settings-section">
          <div class="settings-section-title">Theme</div>
          <div class="settings-card">
            <div class="settings-row">
              <span class="settings-label">Theme</span>
              <div class="settings-value flex gap-4" style="justify-content:flex-end">
                ${['auto', 'dark', 'light', 'high-contrast'].map(t => `
                  <button class="btn btn-ghost ${s.theme === t ? 'btn-primary' : ''}" data-theme="${t}">${t.charAt(0).toUpperCase() + t.slice(1)}</button>
                `).join('')}
              </div>
            </div>
          </div>
        </div>

        <div class="settings-section">
          <div class="settings-section-title">Usage</div>
          <div class="settings-card">
            <div class="stats-bar">
              <div class="stats-bar-header">
                <span>Session tokens</span>
                <span>${state.sessionTokens.toLocaleString()} / ${state.maxSessionTokens.toLocaleString()}</span>
              </div>
              <div class="stats-bar-track">
                <div class="stats-bar-fill ${state.sessionTokens / state.maxSessionTokens > 0.8 ? 'danger' : ''}"
                     style="width:${Math.min(100, (state.sessionTokens / state.maxSessionTokens) * 100)}%"></div>
              </div>
            </div>
          </div>
        </div>

      </div>
      <div class="settings-footer">
        <button class="btn" id="settings-reset">Reset</button>
        <button class="btn btn-primary" id="settings-save">Save</button>
      </div>
    `;

    this.bindEvents();
  }

  private bindEvents(): void {
    // Back
    this.el.querySelector('#settings-back')?.addEventListener('click', () => {
      store.update({ view: 'chat' });
    });

    // Toggles
    const bindToggle = (id: string, key: string) => {
      this.el.querySelector(`#${id}`)?.addEventListener('click', (e) => {
        const btn = e.currentTarget as HTMLElement;
        btn.classList.toggle('on');
        const isOn = btn.classList.contains('on');
        store.updateSettings({ [key]: isOn } as any);
      });
    };
    bindToggle('set-autostart', 'autoStartServer');
    bindToggle('set-autorun', 'autoRun');
    bindToggle('set-confirm', 'requireConfirm');
    bindToggle('set-dryrun', 'dryRun');
    bindToggle('set-superpower', 'superpower');

    // Theme buttons — use event delegation to avoid listener accumulation
    const themeContainer = Array.from(this.el.querySelectorAll('.settings-row')).find(
      row => row.querySelector('[data-theme]')
    ) as HTMLElement | undefined;
    if (themeContainer) {
      themeContainer.onclick = (e) => {
        const btn = (e.target as HTMLElement).closest('[data-theme]') as HTMLElement | null;
        if (!btn) return;
        const theme = btn.dataset.theme!;
        store.updateSettings({ theme });
        document.documentElement.dataset.theme = theme;
        // Update active state without full re-render
        this.el.querySelectorAll('[data-theme]').forEach(b => {
          b.classList.toggle('btn-primary', (b as HTMLElement).dataset.theme === theme);
        });
      };
    }

    // Save
    this.el.querySelector('#settings-save')?.addEventListener('click', () => {
      const serverUrl = (this.el.querySelector('#set-server-url') as HTMLInputElement)?.value;
      const contextWindow = parseInt((this.el.querySelector('#set-context-window') as HTMLInputElement)?.value || '5');
      const state = store.getState();

      store.update({ serverUrl });
      store.updateSettings({ contextWindow });

      saveSettings({ ...state.settings, serverUrl, contextWindow });
      store.update({ view: 'chat' });
    });

    // Reset
    this.el.querySelector('#settings-reset')?.addEventListener('click', () => {
      // Reset to defaults
      store.updateSettings({
        theme: 'auto',
        autoRun: true,
        requireConfirm: true,
        dryRun: false,
        superpower: false,
        contextWindow: 5,
        autoStartServer: false,
      });
      document.documentElement.dataset.theme = 'auto';
      this.render();
    });
  }

  getElement(): HTMLElement {
    return this.el;
  }
}
