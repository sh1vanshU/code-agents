// Code Agents — Chat Commands (open, new chat, switch agent)

import * as vscode from 'vscode';
import { ChatViewProvider } from '../providers/ChatViewProvider';
import { AgentService } from '../services/AgentService';

export function registerChatCommands(
  context: vscode.ExtensionContext,
  chatProvider: ChatViewProvider,
  agentService: AgentService,
): void {
  // Open chat panel
  context.subscriptions.push(
    vscode.commands.registerCommand('codeAgents.openChat', () => {
      vscode.commands.executeCommand('codeAgents.chatView.focus');
    }),
  );

  // New chat
  context.subscriptions.push(
    vscode.commands.registerCommand('codeAgents.newChat', () => {
      chatProvider.postMessage({ type: 'restoreState', state: { messages: [] } });
      vscode.commands.executeCommand('codeAgents.chatView.focus');
    }),
  );

  // Switch agent
  context.subscriptions.push(
    vscode.commands.registerCommand('codeAgents.switchAgent', async () => {
      try {
        const agent = await agentService.showPicker();
        if (agent) {
          chatProvider.postMessage({
            type: 'injectContext',
            text: '',
            agent,
          });
        }
      } catch (err: any) {
        vscode.window.showErrorMessage(`Code Agents: ${err.message || 'Failed to switch agent'}`);
      }
    }),
  );
}
