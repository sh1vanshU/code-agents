// Code Agents — Webview Debug Logger
// Logs to browser console with structured format and optional IDE forwarding

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

const LEVEL_STYLES: Record<LogLevel, string> = {
  debug: 'color: #7a7a94',
  info: 'color: #6366f1',
  warn: 'color: #fbbf24',
  error: 'color: #f87171; font-weight: bold',
};

class WebviewLogger {
  private enabled = true;

  enable(): void { this.enabled = true; }
  disable(): void { this.enabled = false; }

  debug(component: string, message: string, data?: unknown): void {
    this.log('debug', component, message, data);
  }

  info(component: string, message: string, data?: unknown): void {
    this.log('info', component, message, data);
  }

  warn(component: string, message: string, data?: unknown): void {
    this.log('warn', component, message, data);
  }

  error(component: string, message: string, error?: unknown): void {
    this.log('error', component, message, error);
  }

  /** Log state transitions for debugging */
  stateChange(component: string, action: string, detail?: unknown): void {
    this.log('debug', component, `State: ${action}`, detail);
  }

  /** Log message protocol events (IDE <-> Webview) */
  message(direction: 'send' | 'recv', type: string, data?: unknown): void {
    const arrow = direction === 'send' ? '→' : '←';
    this.log('debug', 'Protocol', `${arrow} ${type}`, data);
  }

  private log(level: LogLevel, component: string, message: string, data?: unknown): void {
    if (!this.enabled) return;

    const timestamp = new Date().toISOString().slice(11, 23);
    const prefix = `%c[${timestamp}] [${component}]`;
    const style = LEVEL_STYLES[level];

    if (data !== undefined) {
      console[level](prefix, style, message, data);
    } else {
      console[level](prefix, style, message);
    }
  }
}

export const log = new WebviewLogger();
