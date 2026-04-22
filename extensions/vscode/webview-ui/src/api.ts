// Code Agents — IDE Bridge API
// Unified abstraction over VS Code postMessage and IntelliJ JCEF bridge

export interface IDE {
  postMessage(msg: any): void;
  onMessage(cb: (msg: any) => void): void;
  getState(): any;
  setState(state: any): void;
  platform: 'vscode' | 'intellij' | 'browser';
}

declare function acquireVsCodeApi(): {
  postMessage(msg: any): void;
  getState(): any;
  setState(state: any): void;
};

declare global {
  interface Window {
    ideBridge?: {
      send(msg: string): void;
    };
    _ideCallback?: ((msg: any) => void) | null;
    IDE?: IDE;
  }
}

function createIDE(): IDE {
  // Single listener pattern — prevents accumulating duplicate listeners
  let messageListener: ((e: MessageEvent) => void) | null = null;

  function setMessageListener(cb: (msg: any) => void): void {
    if (messageListener) {
      window.removeEventListener('message', messageListener);
    }
    messageListener = (e: MessageEvent) => cb(e.data);
    window.addEventListener('message', messageListener);
  }

  // VS Code webview
  if (typeof acquireVsCodeApi === 'function') {
    const vscode = acquireVsCodeApi();
    return {
      postMessage: (msg) => vscode.postMessage(msg),
      onMessage: (cb) => setMessageListener(cb),
      getState: () => vscode.getState() || {},
      setState: (s) => vscode.setState(s),
      platform: 'vscode',
    };
  }

  // IntelliJ JCEF
  if (window.ideBridge) {
    return {
      postMessage: (msg) => {
        try {
          if (window.ideBridge) {
            window.ideBridge.send(JSON.stringify(msg));
          }
        } catch (err) {
          console.error('[CodeAgents] Failed to send message:', err);
        }
      },
      onMessage: (cb) => { window._ideCallback = cb; },
      getState: () => {
        try { return JSON.parse(localStorage.getItem('ca-state') || '{}'); }
        catch { return {}; }
      },
      setState: (s) => {
        try { localStorage.setItem('ca-state', JSON.stringify(s)); }
        catch { /* ignore */ }
      },
      platform: 'intellij',
    };
  }

  // Browser fallback (for standalone testing)
  return {
    postMessage: (msg) => console.log('[IDE.postMessage]', msg),
    onMessage: (cb) => {
      setMessageListener(cb);
      (window as any).__ideCallback = cb;
    },
    getState: () => {
      try { return JSON.parse(localStorage.getItem('ca-state') || '{}'); }
      catch { return {}; }
    },
    setState: (s) => {
      try { localStorage.setItem('ca-state', JSON.stringify(s)); }
      catch { /* ignore */ }
    },
    platform: 'browser',
  };
}

export const ide = createIDE();
window.IDE = ide;

// ---- Typed message senders ----

export function sendChatMessage(text: string, agent: string): void {
  ide.postMessage({ type: 'sendMessage', text, agent });
}

export function changeAgent(agent: string): void {
  ide.postMessage({ type: 'changeAgent', agent });
}

export function changeModel(model: string): void {
  ide.postMessage({ type: 'changeModel', model });
}

export function changeMode(mode: 'chat' | 'plan' | 'agent'): void {
  ide.postMessage({ type: 'changeMode', mode });
}

export function clearChat(): void {
  ide.postMessage({ type: 'clearChat' });
}

export function cancelStream(): void {
  ide.postMessage({ type: 'cancelStream' });
}

export function sendSlashCommand(command: string, args: string): void {
  ide.postMessage({ type: 'slashCommand', command, args });
}

export function respondApproval(id: string, approved: boolean): void {
  ide.postMessage({ type: 'approvalResponse', id, approved });
}

export function applyDiff(filePath: string, diff: string): void {
  ide.postMessage({ type: 'applyDiff', filePath, diff });
}

export function openFile(filePath: string, line?: number): void {
  ide.postMessage({ type: 'openFile', filePath, line });
}

export function saveSettings(settings: any): void {
  ide.postMessage({ type: 'saveSettings', settings });
}

export function loadHistory(): void {
  ide.postMessage({ type: 'loadHistory' });
}

export function resumeSession(sessionId: string): void {
  ide.postMessage({ type: 'resumeSession', sessionId });
}

export function exportChat(format: 'markdown' | 'json'): void {
  ide.postMessage({ type: 'exportChat', format });
}

export function queryMentions(query: string, mentionType: 'file' | 'agent'): void {
  ide.postMessage({ type: 'mentionQuery', query, mentionType });
}

export function getTokenUsage(): void {
  ide.postMessage({ type: 'getTokenUsage' });
}
