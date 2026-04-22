// Code Agents — Webview Sidebar Provider

import * as vscode from 'vscode';
import { getNonce, getUri } from '../utils';
import { ApiClient } from '../services/ApiClient';
import { AgentService } from '../services/AgentService';
import { logger } from '../services/Logger';
import type { ToWebview, ToHost } from '../protocol';

interface ChatMessage {
  role: string;
  content: string;
}

export class ChatViewProvider implements vscode.WebviewViewProvider, vscode.Disposable {
  public static readonly viewType = 'codeAgents.chatView';

  private _view?: vscode.WebviewView;
  private messageDisposable?: vscode.Disposable;
  private conversationHistory: ChatMessage[] = [];
  private isStreaming = false;

  constructor(
    private readonly extensionUri: vscode.Uri,
    private readonly apiClient: ApiClient,
    private readonly agentService: AgentService,
  ) {}

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken,
  ): void {
    this._view = webviewView;

    // Dispose previous listener to prevent leaks on re-resolve
    this.messageDisposable?.dispose();

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this.extensionUri],
    };

    webviewView.webview.html = this.getHtml(webviewView.webview);

    // Handle messages from webview — store disposable for cleanup
    this.messageDisposable = webviewView.webview.onDidReceiveMessage((message: ToHost) => {
      logger.debug('ChatView', `Webview message: ${message.type}`);
      this.handleMessage(message).catch((err) => {
        logger.error('ChatView', 'Message handler error', err);
      });
    });

    // Send initial state
    logger.info('ChatView', 'Webview resolved, sending initial agents');
    this.postMessage({ type: 'setAgents', agents: this.agentService.getAgents() });
  }

  /** Post a typed message to the webview (safely no-ops if view not ready) */
  postMessage(message: ToWebview): void {
    if (!this._view?.webview) return;
    this._view.webview.postMessage(message);
  }

  /** Inject context from code actions */
  injectContext(text: string, filePath?: string, fileLines?: string, agent?: string): void {
    if (agent) {
      this.agentService.currentAgent = agent;
    }
    this.postMessage({ type: 'injectContext', text, filePath, fileLines, agent });
    if (this._view) {
      this._view.show(true);
    }
  }

  /** Handle incoming messages from webview */
  private async handleMessage(message: ToHost): Promise<void> {
    try {
      switch (message.type) {
        case 'sendMessage':
          await this.handleSendMessage(message.text, message.agent);
          break;

        case 'changeAgent':
          this.agentService.currentAgent = message.agent;
          break;

        case 'changeModel':
        case 'changeMode':
          // Handled in webview only for now
          break;

        case 'clearChat':
          this.conversationHistory = [];
          break;

        case 'cancelStream':
          this.apiClient.cancelStream();
          this.isStreaming = false;
          this.postMessage({ type: 'streamEnd', fullContent: '' });
          break;

        case 'slashCommand':
          this.postMessage({
            type: 'slashResult',
            command: message.command,
            output: `Command /${message.command} executed.`,
          });
          break;

        case 'openFile':
          await this.openFileInEditor(message.filePath, message.line);
          break;

        case 'applyDiff':
          await this.applyCodeToEditor(message.diff);
          break;

        case 'saveSettings':
          await this.saveSettings(message.settings);
          break;

        case 'exportChat':
          await this.exportConversation(message.format);
          break;

        case 'loadHistory':
          this.postMessage({ type: 'historySessions', sessions: [] });
          break;

        case 'approvalResponse':
        case 'resumeSession':
        case 'mentionQuery':
        case 'getTokenUsage':
          // TODO: implement when server-side support is ready
          break;
      }
    } catch (err: any) {
      console.error(`[CodeAgents] Error handling ${message.type}:`, err);
      vscode.window.showErrorMessage(`Code Agents: ${err.message || 'Unknown error'}`);
    }
  }

  /** Stream a chat message — isStreaming flag always reset via finally */
  private async handleSendMessage(text: string, agent: string): Promise<void> {
    if (this.isStreaming) {
      logger.warn('ChatView', 'Rejected sendMessage — already streaming');
      return;
    }

    logger.info('ChatView', 'Sending message', { agent, textLength: text.length, historySize: this.conversationHistory.length });
    this.isStreaming = true;

    // Use spread copy for API call — don't mutate history until stream completes
    const messagesForApi = [...this.conversationHistory, { role: 'user', content: text }];

    try {
      let streamedContent = '';
      await this.apiClient.streamChat(
        agent,
        messagesForApi,
        (token) => {
          this.postMessage({ type: 'streamToken', token });
        },
        (fullContent) => {
          streamedContent = fullContent;
          this.postMessage({ type: 'streamEnd', fullContent });
        },
        (error) => {
          this.postMessage({ type: 'streamError', error });
        },
      );

      // Only mutate history after stream completes successfully
      this.conversationHistory.push({ role: 'user', content: text });
      if (streamedContent) {
        this.conversationHistory.push({ role: 'assistant', content: streamedContent });
      }
    } catch (err: any) {
      this.postMessage({ type: 'streamError', error: err.message || 'Unknown error' });
    } finally {
      this.isStreaming = false;
    }
  }

  /** Open a file in the editor — validates path stays within workspace */
  private async openFileInEditor(filePath: string, line?: number): Promise<void> {
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (!workspaceFolder) {
      vscode.window.showWarningMessage('No workspace open');
      return;
    }

    // Block path traversal and absolute paths
    if (filePath.includes('..') || filePath.startsWith('/') || filePath.startsWith('\\')) {
      vscode.window.showWarningMessage('Code Agents: Invalid file path');
      return;
    }

    const uri = vscode.Uri.joinPath(workspaceFolder.uri, filePath);

    // Verify resolved path is within workspace
    if (!uri.fsPath.startsWith(workspaceFolder.uri.fsPath)) {
      vscode.window.showWarningMessage('Code Agents: Path outside workspace');
      return;
    }

    try {
      const doc = await vscode.workspace.openTextDocument(uri);
      const editor = await vscode.window.showTextDocument(doc, vscode.ViewColumn.One);

      if (line && line > 0 && line <= doc.lineCount) {
        const position = new vscode.Position(line - 1, 0);
        editor.selection = new vscode.Selection(position, position);
        editor.revealRange(new vscode.Range(position, position));
      }
    } catch (err: any) {
      vscode.window.showErrorMessage(`Failed to open file: ${err.message}`);
    }
  }

  /** Apply code to the active editor */
  private async applyCodeToEditor(code: string): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage('No active editor to apply code to');
      return;
    }

    try {
      await editor.edit((editBuilder) => {
        if (editor.selection.isEmpty) {
          editBuilder.insert(editor.selection.active, code);
        } else {
          editBuilder.replace(editor.selection, code);
        }
      });
    } catch (err: any) {
      vscode.window.showErrorMessage(`Failed to apply code: ${err.message}`);
    }
  }

  /** Save settings to VS Code configuration — await all updates */
  private async saveSettings(settings: any): Promise<void> {
    const config = vscode.workspace.getConfiguration('codeAgents');
    const validKeys = ['serverUrl', 'autoRun', 'requireConfirm', 'theme', 'contextWindow'];
    const updates: Thenable<void>[] = [];

    for (const [key, value] of Object.entries(settings)) {
      if (validKeys.includes(key)) {
        updates.push(config.update(key, value, vscode.ConfigurationTarget.Global));
      }
    }

    await Promise.all(updates);
  }

  /** Export conversation to file */
  private async exportConversation(format: 'markdown' | 'json'): Promise<void> {
    let content: string;
    if (format === 'markdown') {
      content = this.conversationHistory
        .map(m => `## ${m.role === 'user' ? 'You' : 'Agent'}\n\n${m.content}\n`)
        .join('\n---\n\n');
    } else {
      content = JSON.stringify(this.conversationHistory, null, 2);
    }

    const doc = await vscode.workspace.openTextDocument({
      content,
      language: format === 'json' ? 'json' : 'markdown',
    });
    await vscode.window.showTextDocument(doc);
  }

  /** Generate the webview HTML */
  private getHtml(webview: vscode.Webview): string {
    const nonce = getNonce();

    const scriptUri = getUri(webview, this.extensionUri, ['webview-ui', 'build', 'assets', 'index.js']);
    const styleUri = getUri(webview, this.extensionUri, ['webview-ui', 'build', 'assets', 'index.css']);

    const config = vscode.workspace.getConfiguration('codeAgents');
    const theme = config.get<string>('theme', 'auto');

    // Sanitize server URL for CSP — only allow http/https origins
    const rawUrl = config.get<string>('serverUrl', 'http://localhost:8000');
    let connectSrc = 'http://localhost:8000';
    try {
      const parsed = new URL(rawUrl);
      if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
        connectSrc = parsed.origin;
      }
    } catch { /* use default */ }

    return `<!DOCTYPE html>
<html lang="en" data-theme="${theme}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy"
    content="default-src 'none';
      style-src ${webview.cspSource};
      script-src 'nonce-${nonce}';
      connect-src ${connectSrc};">
  <link href="${styleUri}" rel="stylesheet">
  <title>Code Agents</title>
</head>
<body>
  <div id="app"></div>
  <script type="module" nonce="${nonce}" src="${scriptUri}"></script>
</body>
</html>`;
  }

  dispose(): void {
    this.messageDisposable?.dispose();
  }
}
