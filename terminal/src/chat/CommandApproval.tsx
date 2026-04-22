/**
 * CommandApproval — Approve/reject extracted bash commands.
 *
 * Shows extracted commands with syntax highlighting and
 * [y]es / [n]o / [e]dit keybindings.
 */

import React, { useState } from 'react';
import { Box, Text, useInput } from 'ink';
import chalk from 'chalk';

interface Props {
  commands: string[];
  onApprove: (cmds: string[]) => void;
  onReject: () => void;
}

export function CommandApproval({ commands, onApprove, onReject }: Props) {
  const [editing, setEditing] = useState(false);

  useInput((input, key) => {
    if (editing) return;

    if (input === 'y' || input === 'Y') {
      onApprove(commands);
    } else if (input === 'n' || input === 'N') {
      onReject();
    } else if (input === 'e' || input === 'E') {
      // Edit mode — for now, approve as-is (full editor TBD)
      setEditing(true);
      onApprove(commands);
    }
  });

  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor="yellow"
      paddingX={1}
      paddingY={1}
      marginBottom={1}
    >
      <Text color="yellow" bold>Commands to execute:</Text>

      <Box flexDirection="column" marginTop={1}>
        {commands.map((cmd, i) => (
          <Box key={i} marginLeft={1}>
            <Text color="gray">{`${i + 1}. `}</Text>
            <Text>{chalk.cyan('$')} {cmd}</Text>
          </Box>
        ))}
      </Box>

      <Box marginTop={1}>
        <Text color="green" bold>[y]</Text>
        <Text color="gray">es  </Text>
        <Text color="red" bold>[n]</Text>
        <Text color="gray">o  </Text>
        <Text color="blue" bold>[e]</Text>
        <Text color="gray">dit</Text>
      </Box>
    </Box>
  );
}
