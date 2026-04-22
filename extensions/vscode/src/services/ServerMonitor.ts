// Code Agents — Server Health Monitor + Status Bar

import * as vscode from 'vscode';
import { ApiClient } from './ApiClient';

export class ServerMonitor implements vscode.Disposable {
  private statusBarItem: vscode.StatusBarItem;
  private interval: ReturnType<typeof setInterval> | null = null;
  private _connected = false;
  private _onStatusChange = new vscode.EventEmitter<boolean>();
  public readonly onStatusChange = this._onStatusChange.event;

  constructor(private apiClient: ApiClient, private pollingMs: number) {
    this.statusBarItem = vscode.window.createStatusBarItem(
      'codeAgents.serverStatus',
      vscode.StatusBarAlignment.Right,
      50,
    );
    this.statusBarItem.command = 'codeAgents.openChat';
    this.updateDisplay();
    this.statusBarItem.show();
  }

  get connected(): boolean {
    return this._connected;
  }

  startPolling(): void {
    this.check();
    this.interval = setInterval(() => this.check(), this.pollingMs);
  }

  private async check(): Promise<void> {
    const ok = await this.apiClient.checkHealth();
    if (ok !== this._connected) {
      this._connected = ok;
      this.updateDisplay();
      this._onStatusChange.fire(ok);
    }
  }

  private updateDisplay(): void {
    if (this._connected) {
      this.statusBarItem.text = '$(circle-filled) CA';
      this.statusBarItem.tooltip = 'Code Agents: Connected';
      this.statusBarItem.backgroundColor = undefined;
    } else {
      this.statusBarItem.text = '$(circle-outline) CA';
      this.statusBarItem.tooltip = 'Code Agents: Disconnected';
      this.statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
    }
  }

  dispose(): void {
    if (this.interval) {
      clearInterval(this.interval);
    }
    this.statusBarItem.dispose();
    this._onStatusChange.dispose();
  }
}
