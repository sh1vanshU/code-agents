// Code Agents — Utility functions

import * as vscode from 'vscode';
import * as crypto from 'crypto';

/** Generate a cryptographically secure nonce for CSP */
export function getNonce(): string {
  return crypto.randomBytes(16).toString('hex');
}

/** Get a webview URI for a resource */
export function getUri(webview: vscode.Webview, extensionUri: vscode.Uri, pathList: string[]): vscode.Uri {
  return webview.asWebviewUri(vscode.Uri.joinPath(extensionUri, ...pathList));
}
