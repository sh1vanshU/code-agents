// Code Agents — VS Code Extension Entry Point

import * as vscode from 'vscode';
import { ChatViewProvider } from './providers/ChatViewProvider';
import { ApiClient } from './services/ApiClient';
import { AgentService } from './services/AgentService';
import { ServerMonitor } from './services/ServerMonitor';
import { logger } from './services/Logger';
import { registerCodeActions } from './commands/codeActions';
import { registerChatCommands } from './commands/chatCommands';

export function activate(context: vscode.ExtensionContext): void {
  const config = vscode.workspace.getConfiguration('codeAgents');

  // Initialize services
  const serverUrl = config.get<string>('serverUrl', 'http://localhost:8000');
  const defaultAgent = config.get<string>('defaultAgent', 'auto-pilot');
  const pollingInterval = Math.max(config.get<number>('statusPollingInterval', 15000), 1000);

  logger.info('Extension', 'Activating Code Agents', { serverUrl, defaultAgent, pollingInterval });

  const apiClient = new ApiClient(serverUrl);
  const agentService = new AgentService(defaultAgent);
  const serverMonitor = new ServerMonitor(apiClient, pollingInterval);

  // Create the webview provider
  const chatProvider = new ChatViewProvider(context.extensionUri, apiClient, agentService);

  // Register webview provider
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(ChatViewProvider.viewType, chatProvider),
  );

  // Register commands
  registerChatCommands(context, chatProvider, agentService);
  registerCodeActions(context, chatProvider, agentService);
  logger.debug('Extension', 'Commands registered');

  // Start server monitoring — push to subscriptions FIRST for safe disposal
  context.subscriptions.push(serverMonitor);
  serverMonitor.startPolling();

  // Forward server status to webview + refresh agents on connect
  serverMonitor.onStatusChange((connected) => {
    logger.info('ServerMonitor', `Server ${connected ? 'connected' : 'disconnected'}`);
    chatProvider.postMessage({ type: 'serverStatus', connected });
    if (connected) {
      agentService.refreshAgents(apiClient)
        .then(() => {
          const agents = agentService.getAgents();
          logger.debug('AgentService', `Loaded ${agents.length} agents`);
          chatProvider.postMessage({ type: 'setAgents', agents });
        })
        .catch((err) => {
          logger.error('AgentService', 'Failed to refresh agents', err);
        });
    }
  });

  // Listen for configuration changes
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      try {
        if (e.affectsConfiguration('codeAgents.serverUrl')) {
          const newUrl = vscode.workspace.getConfiguration('codeAgents').get<string>('serverUrl', 'http://localhost:8000');
          try {
            new URL(newUrl);
            logger.info('Config', 'Server URL changed', { newUrl });
            apiClient.setServerUrl(newUrl);
          } catch {
            logger.error('Config', 'Invalid server URL', new Error(newUrl));
          }
        }
        if (e.affectsConfiguration('codeAgents.theme')) {
          const theme = vscode.workspace.getConfiguration('codeAgents').get<string>('theme', 'auto');
          logger.debug('Config', 'Theme changed', { theme });
          chatProvider.postMessage({ type: 'themeChanged', theme });
        }
      } catch (err) {
        logger.error('Config', 'Configuration change error', err);
      }
    }),
  );

  // Auto-start server if configured
  if (config.get<boolean>('autoStartServer', false)) {
    logger.info('Extension', 'Auto-starting server');
    autoStartServer();
  }

  // Clean up services on deactivation
  context.subscriptions.push(
    { dispose: () => agentService.dispose() },
    chatProvider,
    logger,
  );

  logger.info('Extension', 'Code Agents activated');
}

/** Try to start the code-agents server in the background */
function autoStartServer(): void {
  const { spawn } = require('child_process');
  try {
    const proc = spawn('code-agents', ['start'], {
      detached: true,
      stdio: 'ignore',
    });
    proc.unref();
    logger.debug('Extension', 'Server process spawned');
  } catch (err) {
    logger.warn('Extension', 'Failed to auto-start server (may already be running)', { error: String(err) });
  }
}

export function deactivate(): void {
  logger.info('Extension', 'Code Agents deactivated');
}
