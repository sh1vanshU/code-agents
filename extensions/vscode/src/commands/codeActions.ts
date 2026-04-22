// Code Agents — Right-click Context Menu Code Actions

import * as vscode from 'vscode';
import { ChatViewProvider } from '../providers/ChatViewProvider';
import { AgentService } from '../services/AgentService';

interface CodeAction {
  command: string;
  agent: string;
  promptPrefix: string;
}

const CODE_ACTIONS: CodeAction[] = [
  { command: 'codeAgents.reviewCode', agent: 'code-reviewer', promptPrefix: 'Review this code for bugs, security issues, and improvements' },
  { command: 'codeAgents.writeTests', agent: 'code-tester', promptPrefix: 'Write comprehensive tests for this code' },
  { command: 'codeAgents.explainCode', agent: 'code-reasoning', promptPrefix: 'Explain what this code does, its architecture, and design patterns' },
  { command: 'codeAgents.fixCode', agent: 'code-writer', promptPrefix: 'Fix any bugs or issues in this code' },
  { command: 'codeAgents.securityScan', agent: 'security', promptPrefix: 'Run a security audit on this code (OWASP, CVE, secrets)' },
  { command: 'codeAgents.buildDeploy', agent: 'jenkins-cicd', promptPrefix: 'Build and deploy the current project' },
];

export function registerCodeActions(
  context: vscode.ExtensionContext,
  chatProvider: ChatViewProvider,
  agentService: AgentService,
): void {
  for (const action of CODE_ACTIONS) {
    const disposable = vscode.commands.registerCommand(action.command, () => {
      try {
        const editor = vscode.window.activeTextEditor;

        if (action.command === 'codeAgents.buildDeploy') {
          const workspaceName = vscode.workspace.workspaceFolders?.[0]?.name || 'project';
          chatProvider.injectContext(
            `${action.promptPrefix}: ${workspaceName}`,
            undefined,
            undefined,
            action.agent,
          );
          return;
        }

        if (!editor) {
          vscode.window.showWarningMessage('No active editor');
          return;
        }

        const selection = editor.document.getText(editor.selection);
        const filePath = vscode.workspace.asRelativePath(editor.document.uri);
        const languageId = editor.document.languageId;

        let startLine: number | undefined;
        let endLine: number | undefined;
        if (!editor.selection.isEmpty) {
          startLine = editor.selection.start.line + 1;
          endLine = editor.selection.end.line + 1;
        }

        const fileLines = startLine && endLine ? `lines ${startLine}-${endLine}` : undefined;
        const codeBlock = selection
          ? `\n\n\`\`\`${languageId}\n${selection}\n\`\`\``
          : '';

        chatProvider.injectContext(
          `${action.promptPrefix}:${codeBlock}`,
          filePath,
          fileLines,
          action.agent,
        );
      } catch (err: any) {
        vscode.window.showErrorMessage(`Code Agents: ${err.message || 'Action failed'}`);
      }
    });

    context.subscriptions.push(disposable);
  }

  // Add to Chat (generic — no agent switch)
  context.subscriptions.push(
    vscode.commands.registerCommand('codeAgents.addToChat', () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) return;

      const selection = editor.document.getText(editor.selection);
      const filePath = vscode.workspace.asRelativePath(editor.document.uri);

      if (selection) {
        const languageId = editor.document.languageId;
        const startLine = editor.selection.start.line + 1;
        const endLine = editor.selection.end.line + 1;
        chatProvider.injectContext(
          `\`\`\`${languageId}\n${selection}\n\`\`\``,
          filePath,
          `lines ${startLine}-${endLine}`,
        );
      } else {
        chatProvider.injectContext('', filePath);
      }
    }),
  );
}
