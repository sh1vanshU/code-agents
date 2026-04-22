declare module 'marked-terminal' {
  interface TerminalRendererOptions {
    tab?: number;
    width?: number;
    reflowText?: boolean;
    showSectionPrefix?: boolean;
    unescape?: boolean;
  }

  export function markedTerminal(options?: TerminalRendererOptions): any;
  export default function TerminalRenderer(options?: TerminalRendererOptions): any;
}
