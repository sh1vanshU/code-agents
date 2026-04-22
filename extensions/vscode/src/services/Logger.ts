// Code Agents — Structured Logger for VS Code Extension

import * as vscode from 'vscode';

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

const LEVEL_PRIORITY: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

class Logger {
  private channel: vscode.OutputChannel;
  private minLevel: LogLevel = 'debug';

  constructor() {
    this.channel = vscode.window.createOutputChannel('Code Agents', { log: true });
  }

  setLevel(level: LogLevel): void {
    this.minLevel = level;
  }

  debug(component: string, message: string, data?: Record<string, unknown>): void {
    this.log('debug', component, message, data);
  }

  info(component: string, message: string, data?: Record<string, unknown>): void {
    this.log('info', component, message, data);
  }

  warn(component: string, message: string, data?: Record<string, unknown>): void {
    this.log('warn', component, message, data);
  }

  error(component: string, message: string, error?: unknown, data?: Record<string, unknown>): void {
    const errMsg = error instanceof Error ? error.message : String(error || '');
    const errStack = error instanceof Error ? error.stack : undefined;
    this.log('error', component, message, { ...data, error: errMsg, stack: errStack });
  }

  /** Show the output channel to the user */
  show(): void {
    this.channel.show(true);
  }

  dispose(): void {
    this.channel.dispose();
  }

  private log(level: LogLevel, component: string, message: string, data?: Record<string, unknown>): void {
    if (LEVEL_PRIORITY[level] < LEVEL_PRIORITY[this.minLevel]) return;

    const timestamp = new Date().toISOString();
    const prefix = `[${timestamp}] [${level.toUpperCase()}] [${component}]`;
    const dataStr = data ? ` ${JSON.stringify(data)}` : '';
    const line = `${prefix} ${message}${dataStr}`;

    switch (level) {
      case 'debug': this.channel.appendLine(line); break;
      case 'info': this.channel.appendLine(line); break;
      case 'warn': this.channel.appendLine(line); break;
      case 'error': this.channel.appendLine(line); break;
    }
  }
}

export const logger = new Logger();
