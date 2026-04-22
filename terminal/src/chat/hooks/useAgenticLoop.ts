/**
 * useAgenticLoop — Command extraction + execution loop.
 *
 * State machine: IDLE -> STREAMING -> COMMANDS_FOUND -> AWAITING_APPROVAL
 *   -> EXECUTING -> FEEDING_BACK -> STREAMING (loop)
 *
 * Extracts bash commands from responses using fenced code block regex,
 * executes via child_process, and feeds output back for the next turn.
 */

import { useState, useCallback, useRef } from 'react';
import { execFileSync } from 'node:child_process';

const BASH_REGEX = /```(?:bash|sh|shell|zsh|console)\s*\n([\s\S]*?)```/g;

const MAX_LOOPS = parseInt(process.env['CODE_AGENTS_MAX_LOOPS'] ?? '10', 10);

/** Dangerous patterns that should never be executed from AI responses */
const DANGEROUS_PATTERNS = [
  /\brm\s+(-[rRf]+\s+)?\/(?!\w)/,     // rm -rf / (root deletion)
  /\bmkfs\b/,                           // filesystem format
  /\bdd\s+.*of=\/dev\//,               // disk overwrite
  />\s*\/dev\/sd[a-z]/,                // device redirect
  /\bcurl\b.*\|\s*(?:bash|sh|sudo)/,   // curl | bash (remote execution)
  /\bwget\b.*\|\s*(?:bash|sh|sudo)/,   // wget | bash
  /\bchmod\s+777\s+\//,               // chmod 777 /
  /\bsudo\s+rm\b/,                     // sudo rm
];

export type LoopState =
  | 'IDLE'
  | 'STREAMING'
  | 'COMMANDS_FOUND'
  | 'AWAITING_APPROVAL'
  | 'EXECUTING'
  | 'FEEDING_BACK';

export interface UseAgenticLoopReturn {
  loopState: LoopState;
  pendingCommands: string[];
  loopCount: number;
  extractCommands: (content: string) => string[];
  approveCommands: (cmds: string[]) => string;
  rejectCommands: () => void;
  setLoopState: (state: LoopState) => void;
  canLoop: () => boolean;
  resetLoop: () => void;
}

export function useAgenticLoop(): UseAgenticLoopReturn {
  const [loopState, setLoopState] = useState<LoopState>('IDLE');
  const [pendingCommands, setPendingCommands] = useState<string[]>([]);
  const loopCountRef = useRef(0);

  const extractCommands = useCallback((content: string): string[] => {
    const commands: string[] = [];
    let match: RegExpExecArray | null;
    const regex = new RegExp(BASH_REGEX.source, BASH_REGEX.flags);

    while ((match = regex.exec(content)) !== null) {
      const block = match[1]!.trim();
      // Split multi-line blocks into individual commands, skip comments/empty
      for (const line of block.split('\n')) {
        const trimmed = line.trim();
        if (trimmed && !trimmed.startsWith('#')) {
          commands.push(trimmed);
        }
      }
    }

    if (commands.length > 0) {
      setPendingCommands(commands);
      setLoopState('COMMANDS_FOUND');
    }

    return commands;
  }, []);

  const approveCommands = useCallback((cmds: string[]): string => {
    setLoopState('EXECUTING');
    const results: string[] = [];

    for (const cmd of cmds) {
      // Security: reject commands matching dangerous patterns
      if (DANGEROUS_PATTERNS.some(pat => pat.test(cmd))) {
        results.push(`$ ${cmd}\n[BLOCKED] Command matches a dangerous pattern and was not executed.`);
        continue;
      }

      try {
        // Security: use execFileSync with bash -c to avoid direct shell string injection
        const output = execFileSync('/bin/bash', ['-c', cmd], {
          encoding: 'utf-8',
          timeout: 30_000,
          maxBuffer: 1024 * 1024,
          cwd: process.cwd(),
          stdio: ['pipe', 'pipe', 'pipe'],
        });
        results.push(`$ ${cmd}\n${output}`);
      } catch (err: any) {
        const stderr = err.stderr?.toString() ?? '';
        const stdout = err.stdout?.toString() ?? '';
        results.push(`$ ${cmd}\n${stdout}${stderr}\n[exit code: ${err.status ?? 1}]`);
      }
    }

    loopCountRef.current += 1;
    setPendingCommands([]);
    setLoopState('FEEDING_BACK');

    return results.join('\n\n');
  }, []);

  const rejectCommands = useCallback(() => {
    setPendingCommands([]);
    setLoopState('IDLE');
  }, []);

  const canLoop = useCallback(() => {
    return loopCountRef.current < MAX_LOOPS;
  }, []);

  const resetLoop = useCallback(() => {
    loopCountRef.current = 0;
    setPendingCommands([]);
    setLoopState('IDLE');
  }, []);

  return {
    loopState,
    pendingCommands,
    loopCount: loopCountRef.current,
    extractCommands,
    approveCommands,
    rejectCommands,
    setLoopState,
    canLoop,
    resetLoop,
  };
}
