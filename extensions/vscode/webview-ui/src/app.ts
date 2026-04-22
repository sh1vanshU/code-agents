// Code Agents — Root App (view router + message handler)

import { store } from './state';
import { ide } from './api';
import { log } from './logger';
import { ApprovalCard } from './components/ApprovalCard';
import { ChatView } from './views/ChatView';
import { SettingsView } from './views/SettingsView';
import { HistoryView } from './views/HistoryView';

export class App {
  private chatView: ChatView;
  private settingsView: SettingsView;
  private historyView: HistoryView;

  constructor(root: HTMLElement) {
    this.chatView = new ChatView();
    this.settingsView = new SettingsView();
    this.historyView = new HistoryView();

    // Mount views
    this.chatView.mount(root);
    this.settingsView.mount(root);
    this.historyView.mount(root);

    // Listen for messages from IDE host
    ide.onMessage((msg) => this.handleMessage(msg));

    // Restore state
    const saved = ide.getState();
    if (saved && saved.messages) {
      store.update({
        messages: saved.messages,
        currentAgent: saved.currentAgent || 'auto-pilot',
      });
    }

    // Auto-save state on changes
    store.subscribe((state) => {
      ide.setState({
        messages: state.messages.slice(-50), // Keep last 50 messages
        currentAgent: state.currentAgent,
      });
    });

    // Apply saved theme
    const theme = store.getState().settings.theme;
    document.documentElement.dataset.theme = theme;
  }

  private handleMessage(msg: any): void {
    if (!msg || !msg.type) return;
    if (msg.type !== 'streamToken') { // Don't spam logs with every token
      log.message('recv', msg.type, msg.type === 'streamEnd' ? { contentLength: msg.fullContent?.length } : undefined);
    }

    switch (msg.type) {
      case 'streamToken': {
        const prevState = store.getState();
        if (!prevState.isStreaming) {
          // Start streaming — add placeholder assistant message
          store.update({ isStreaming: true, streamingContent: msg.token });
          store.addMessage({
            id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
            role: 'assistant',
            content: msg.token,
            agent: prevState.currentAgent,
            timestamp: Date.now(),
          });
        } else {
          // Append token — re-read state after the isStreaming check to avoid stale content
          const currentContent = store.getState().streamingContent + msg.token;
          store.update({ streamingContent: currentContent });
          store.updateLastMessage(currentContent);
        }
        break;
      }

      case 'streamEnd': {
        store.update({ isStreaming: false, streamingContent: '' });
        if (msg.fullContent) {
          store.updateLastMessage(msg.fullContent);
        }
        break;
      }

      case 'streamError': {
        store.update({ isStreaming: false, streamingContent: '' });
        store.addMessage({
          id: Date.now().toString(36),
          role: 'error',
          content: msg.error || 'An error occurred',
          timestamp: Date.now(),
        });
        break;
      }

      case 'serverStatus': {
        store.update({ connected: msg.connected });
        break;
      }

      case 'setAgents': {
        if (Array.isArray(msg.agents) && msg.agents.length > 0) {
          store.update({ agents: msg.agents });
        }
        break;
      }

      case 'injectContext': {
        // Context injection from right-click actions
        if (msg.agent) {
          store.update({ currentAgent: msg.agent });
        }
        if (msg.filePath) {
          store.addContextFile(msg.filePath, msg.fileLines);
        }
        if (msg.text) {
          this.chatView.setInput(msg.text);
        }
        store.update({ view: 'chat' });
        this.chatView.focus();
        break;
      }

      case 'planUpdate': {
        store.update({ plan: msg.plan, mode: 'plan' });
        break;
      }

      case 'approvalRequest': {
        const approval: import('./state').ApprovalRequest = {
          id: msg.id,
          command: msg.command,
          agent: msg.agent || store.getState().currentAgent,
        };
        store.update({ pendingApproval: approval });

        // Render ApprovalCard inline in the message list
        const card = new ApprovalCard(approval);
        const messagesEl = document.getElementById('messages');
        if (messagesEl) {
          messagesEl.appendChild(card.getElement());
          messagesEl.scrollTop = messagesEl.scrollHeight;
        }
        break;
      }

      case 'slashResult': {
        store.addMessage({
          id: Date.now().toString(36),
          role: 'assistant',
          content: msg.output,
          agent: store.getState().currentAgent,
          timestamp: Date.now(),
        });
        break;
      }

      case 'themeChanged': {
        document.documentElement.dataset.theme = msg.theme;
        store.updateSettings({ theme: msg.theme });
        break;
      }

      case 'restoreState': {
        if (msg.state && typeof msg.state === 'object') {
          // Only allow known safe keys to prevent state injection
          const allowed = ['messages', 'currentAgent', 'connected', 'serverUrl', 'agents', 'settings', 'mode'];
          const filtered: Record<string, unknown> = {};
          for (const key of allowed) {
            if (key in msg.state) {
              filtered[key] = msg.state[key];
            }
          }
          store.update(filtered as Partial<import('./state').AppState>);
        }
        break;
      }

      case 'historySessions': {
        this.historyView.setSessions(msg.sessions || []);
        break;
      }

      case 'tokenUsage': {
        store.update({
          sessionTokens: msg.sessionTokens || 0,
          maxSessionTokens: msg.maxSessionTokens || 100000,
        });
        break;
      }
    }
  }
}
