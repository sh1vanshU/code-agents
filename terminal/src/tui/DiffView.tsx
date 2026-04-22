/**
 * DiffView — Side-by-side or inline diff display with colors.
 */

import React from 'react';
import { Box, Text } from 'ink';

interface DiffLine {
  type: 'add' | 'remove' | 'context';
  content: string;
  lineNumber?: number;
}

interface Props {
  lines: DiffLine[];
  fileName?: string;
}

export function DiffView({ lines, fileName }: Props) {
  return (
    <Box flexDirection="column" borderStyle="single" borderColor="gray" paddingX={1}>
      {fileName && (
        <Text bold color="cyan">{fileName}</Text>
      )}
      {lines.map((line, i) => {
        const prefix = line.type === 'add' ? '+' : line.type === 'remove' ? '-' : ' ';
        const color = line.type === 'add' ? 'green' : line.type === 'remove' ? 'red' : undefined;
        const bg = line.type === 'add' ? 'greenBright' : line.type === 'remove' ? 'redBright' : undefined;

        return (
          <Box key={i}>
            {line.lineNumber !== undefined && (
              <Text color="gray" dimColor>{String(line.lineNumber).padStart(4)} </Text>
            )}
            <Text color={color} backgroundColor={bg ? undefined : undefined}>
              {prefix} {line.content}
            </Text>
          </Box>
        );
      })}
    </Box>
  );
}

/** Parse a unified diff string into DiffLine[] */
export function parseDiff(diffText: string): DiffLine[] {
  return diffText.split('\n').map((line) => {
    if (line.startsWith('+') && !line.startsWith('+++')) {
      return { type: 'add', content: line.slice(1) };
    }
    if (line.startsWith('-') && !line.startsWith('---')) {
      return { type: 'remove', content: line.slice(1) };
    }
    return { type: 'context', content: line.startsWith(' ') ? line.slice(1) : line };
  });
}
