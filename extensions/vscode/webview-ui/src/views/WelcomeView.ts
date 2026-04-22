// Code Agents — Welcome View

import { store } from '../state';
import { sendChatMessage, changeAgent } from '../api';

interface QuickAction {
  icon: string;
  label: string;
  agent: string;
  prompt: string;
}

const QUICK_ACTIONS: QuickAction[] = [
  { icon: '&#128221;', label: 'Review', agent: 'code-reviewer', prompt: 'Review the latest changes for bugs and security issues' },
  { icon: '&#129514;', label: 'Test', agent: 'code-tester', prompt: 'Write comprehensive tests for the current file' },
  { icon: '&#128269;', label: 'Explain', agent: 'code-reasoning', prompt: 'Explain the architecture and code flow of this project' },
  { icon: '&#128640;', label: 'Deploy', agent: 'jenkins-cicd', prompt: 'Build and deploy the current project' },
  { icon: '&#128737;', label: 'Secure', agent: 'security', prompt: 'Run a security audit (OWASP, CVE, secrets detection)' },
  { icon: '&#128295;', label: 'Fix', agent: 'code-writer', prompt: 'Fix the bugs in the current file' },
];

export class WelcomeView {
  private el: HTMLElement;

  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'welcome';
    this.el.id = 'welcome';
    this.render();
  }

  mount(parent: HTMLElement): void {
    parent.appendChild(this.el);
  }

  private render(): void {
    this.el.innerHTML = `
      <div class="welcome-logo">Code Agents</div>
      <div class="welcome-subtitle">13 specialist agents at your service. Select an agent or use a quick action to get started.</div>
      <div class="quick-actions">
        ${QUICK_ACTIONS.map(a => `
          <button class="quick-action" data-agent="${a.agent}" data-prompt="${a.prompt}">
            <span class="qa-icon">${a.icon}</span>
            <span class="qa-label">${a.label}</span>
          </button>
        `).join('')}
      </div>
    `;

    this.el.querySelectorAll('.quick-action').forEach(btn => {
      btn.addEventListener('click', () => {
        const agent = (btn as HTMLElement).dataset.agent!;
        const prompt = (btn as HTMLElement).dataset.prompt!;

        // Switch agent
        store.update({ currentAgent: agent });
        changeAgent(agent);

        // Add user message
        store.addMessage({
          id: Date.now().toString(36),
          role: 'user',
          content: prompt,
          timestamp: Date.now(),
        });

        // Send
        sendChatMessage(prompt, agent);

        // Hide welcome
        this.el.style.display = 'none';
      });
    });
  }

  show(): void { this.el.style.display = ''; }
  hide(): void { this.el.style.display = 'none'; }

  getElement(): HTMLElement {
    return this.el;
  }
}
