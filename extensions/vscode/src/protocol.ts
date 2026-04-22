// Code Agents — Typed Message Protocol (Host <-> Webview)

export interface Agent {
  name: string;
  description: string;
}

export interface PlanStep {
  text: string;
  status: 'pending' | 'current' | 'completed' | 'failed';
}

export interface PlanState {
  title: string;
  status: string;
  steps: PlanStep[];
  currentStep: number;
}

export interface SessionInfo {
  id: string;
  title: string;
  agent: string;
  messageCount: number;
  timestamp: number;
}

// ---- Host -> Webview ----

export type ToWebview =
  | { type: 'streamToken'; token: string }
  | { type: 'streamEnd'; fullContent: string }
  | { type: 'streamError'; error: string }
  | { type: 'serverStatus'; connected: boolean }
  | { type: 'setAgents'; agents: Agent[] }
  | { type: 'injectContext'; text: string; filePath?: string; fileLines?: string; agent?: string }
  | { type: 'planUpdate'; plan: PlanState }
  | { type: 'approvalRequest'; id: string; command: string; agent?: string }
  | { type: 'slashResult'; command: string; output: string }
  | { type: 'themeChanged'; theme: string }
  | { type: 'restoreState'; state: any }
  | { type: 'historySessions'; sessions: SessionInfo[] }
  | { type: 'tokenUsage'; sessionTokens: number; maxSessionTokens: number };

// ---- Webview -> Host ----

export type ToHost =
  | { type: 'sendMessage'; text: string; agent: string }
  | { type: 'changeAgent'; agent: string }
  | { type: 'changeModel'; model: string }
  | { type: 'changeMode'; mode: 'chat' | 'plan' | 'agent' }
  | { type: 'clearChat' }
  | { type: 'cancelStream' }
  | { type: 'slashCommand'; command: string; args: string }
  | { type: 'approvalResponse'; id: string; approved: boolean }
  | { type: 'applyDiff'; filePath: string; diff: string }
  | { type: 'openFile'; filePath: string; line?: number }
  | { type: 'saveSettings'; settings: any }
  | { type: 'loadHistory' }
  | { type: 'resumeSession'; sessionId: string }
  | { type: 'exportChat'; format: 'markdown' | 'json' }
  | { type: 'mentionQuery'; query: string; mentionType: 'file' | 'agent' }
  | { type: 'getTokenUsage' };
