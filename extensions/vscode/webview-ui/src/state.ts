// Code Agents — Reactive State Store

export interface Agent {
  name: string;
  description: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'error' | 'system';
  content: string;
  agent?: string;
  timestamp: number;
  filePath?: string;
  fileLines?: string;
}

export interface PlanStep {
  text: string;
  status: 'pending' | 'current' | 'completed' | 'failed';
}

export interface PlanState {
  title: string;
  status: 'draft' | 'proposed' | 'approved' | 'executing' | 'completed' | 'rejected';
  steps: PlanStep[];
  currentStep: number;
}

export interface ApprovalRequest {
  id: string;
  command: string;
  agent: string;
}

export interface SessionInfo {
  id: string;
  title: string;
  agent: string;
  messageCount: number;
  timestamp: number;
}

export type ViewState = 'chat' | 'settings' | 'history';
export type ModeState = 'chat' | 'plan' | 'agent';

export interface AppState {
  // Connection
  connected: boolean;
  serverUrl: string;

  // Agent & model
  agents: Agent[];
  currentAgent: string;
  currentModel: string;
  mode: ModeState;

  // Chat
  messages: Message[];
  isStreaming: boolean;
  streamingContent: string;

  // UI
  view: ViewState;
  showSlashPalette: boolean;
  showMentionPicker: boolean;
  showAgentPicker: boolean;
  slashFilter: string;
  mentionFilter: string;

  // Context
  contextFiles: { path: string; lines?: string }[];

  // Plan
  plan: PlanState | null;

  // Approvals
  pendingApproval: ApprovalRequest | null;

  // Token usage
  sessionTokens: number;
  maxSessionTokens: number;

  // Settings
  settings: {
    theme: string;
    autoRun: boolean;
    requireConfirm: boolean;
    dryRun: boolean;
    superpower: boolean;
    contextWindow: number;
    autoStartServer: boolean;
  };
}

type Listener = (state: AppState) => void;

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

const initialState: AppState = {
  connected: false,
  serverUrl: 'http://localhost:8000',
  agents: DEFAULT_AGENTS,
  currentAgent: 'auto-pilot',
  currentModel: '',
  mode: 'chat',
  messages: [],
  isStreaming: false,
  streamingContent: '',
  view: 'chat',
  showSlashPalette: false,
  showMentionPicker: false,
  showAgentPicker: false,
  slashFilter: '',
  mentionFilter: '',
  contextFiles: [],
  plan: null,
  pendingApproval: null,
  sessionTokens: 0,
  maxSessionTokens: 100000,
  settings: {
    theme: 'auto',
    autoRun: true,
    requireConfirm: true,
    dryRun: false,
    superpower: false,
    contextWindow: 5,
    autoStartServer: false,
  },
};

class Store {
  private state: AppState;
  private listeners: Set<Listener> = new Set();

  constructor() {
    this.state = { ...initialState };
  }

  getState(): AppState {
    return { ...this.state };
  }

  update(partial: Partial<AppState>): void {
    this.state = { ...this.state, ...partial };
    this.notify();
  }

  updateSettings(partial: Partial<AppState['settings']>): void {
    this.state = {
      ...this.state,
      settings: { ...this.state.settings, ...partial },
    };
    this.notify();
  }

  addMessage(msg: Message): void {
    this.state = {
      ...this.state,
      messages: [...this.state.messages, msg],
    };
    this.notify();
  }

  updateLastMessage(content: string): void {
    const msgs = [...this.state.messages];
    if (msgs.length > 0) {
      msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content };
    }
    this.state = { ...this.state, messages: msgs };
    this.notify();
  }

  clearMessages(): void {
    this.state = { ...this.state, messages: [], plan: null, pendingApproval: null };
    this.notify();
  }

  addContextFile(path: string, lines?: string): void {
    const exists = this.state.contextFiles.some(f => f.path === path);
    if (!exists) {
      this.state = {
        ...this.state,
        contextFiles: [...this.state.contextFiles, { path, lines }],
      };
      this.notify();
    }
  }

  removeContextFile(path: string): void {
    this.state = {
      ...this.state,
      contextFiles: this.state.contextFiles.filter(f => f.path !== path),
    };
    this.notify();
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(): void {
    for (const listener of this.listeners) {
      listener(this.state);
    }
  }

  /** Generate a unique message ID */
  static msgId(): string {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  }
}

export const store = new Store();
export const msgId = Store.msgId;
export { DEFAULT_AGENTS };
