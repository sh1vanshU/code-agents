// Code Agents — Agent Service

import * as vscode from 'vscode';
import { ApiClient } from './ApiClient';
import type { Agent } from '../protocol';

const DEFAULT_AGENTS: Agent[] = [
  { name: 'auto-pilot', description: 'Full SDLC orchestration' },
  { name: 'code-writer', description: 'Generate & modify code' },
  { name: 'code-reviewer', description: 'Review, bugs, security' },
  { name: 'code-reasoning', description: 'Analysis & exploration' },
  { name: 'code-tester', description: 'Write tests, debug' },
  { name: 'test-coverage', description: 'Coverage analysis' },
  { name: 'qa-regression', description: 'Full regression suites' },
  { name: 'jenkins-cicd', description: 'Build & deploy' },
  { name: 'argocd-verify', description: 'Deployment verification' },
  { name: 'git-ops', description: 'Git workflows' },
  { name: 'jira-ops', description: 'Jira & Confluence' },
  { name: 'redash-query', description: 'SQL via Redash' },
  { name: 'security', description: 'OWASP scanning' },
];

export class AgentService {
  private agents: Agent[] = DEFAULT_AGENTS;
  private _currentAgent: string;
  private statusBarItem: vscode.StatusBarItem;

  constructor(defaultAgent: string) {
    this._currentAgent = defaultAgent;

    this.statusBarItem = vscode.window.createStatusBarItem(
      'codeAgents.agentSelector',
      vscode.StatusBarAlignment.Left,
      100,
    );
    this.statusBarItem.command = 'codeAgents.switchAgent';
    this.updateDisplay();
    this.statusBarItem.show();
  }

  get currentAgent(): string {
    return this._currentAgent;
  }

  set currentAgent(agent: string) {
    this._currentAgent = agent;
    this.updateDisplay();
  }

  getAgents(): Agent[] {
    return this.agents;
  }

  async refreshAgents(apiClient: ApiClient): Promise<void> {
    const fetched = await apiClient.getAgents();
    if (fetched.length > 0) {
      this.agents = fetched;
    }
  }

  async showPicker(): Promise<string | undefined> {
    const items = this.agents.map(a => ({
      label: a.name,
      description: a.description,
    }));

    const picked = await vscode.window.showQuickPick(items, {
      placeHolder: 'Select an agent',
      title: 'Code Agents — Switch Agent',
    });

    if (picked && this.agents.some(a => a.name === picked.label)) {
      this.currentAgent = picked.label;
      return picked.label;
    }
    return undefined;
  }

  private updateDisplay(): void {
    this.statusBarItem.text = `$(hubot) ${this._currentAgent}`;
    this.statusBarItem.tooltip = `Code Agents: ${this._currentAgent} (click to switch)`;
  }

  dispose(): void {
    this.statusBarItem.dispose();
  }
}
