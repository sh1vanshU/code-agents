/**
 * FileTree — Collapsible project file tree display.
 */

import React, { useState } from 'react';
import { Box, Text, useInput } from 'ink';

interface FileNode {
  name: string;
  type: 'file' | 'directory';
  children?: FileNode[];
}

interface Props {
  tree: FileNode[];
  onSelect?: (path: string) => void;
}

function TreeItem({ node, depth, selected, onSelect }: {
  node: FileNode;
  depth: number;
  selected: boolean;
  onSelect?: (path: string) => void;
}) {
  const [expanded, setExpanded] = useState(depth < 1);
  const indent = '  '.repeat(depth);
  const icon = node.type === 'directory'
    ? (expanded ? '📂' : '📁')
    : '📄';

  return (
    <Box flexDirection="column">
      <Text
        color={selected ? 'cyan' : node.type === 'directory' ? 'blue' : undefined}
        bold={selected}
      >
        {indent}{icon} {node.name}
      </Text>
      {expanded && node.children?.map((child, i) => (
        <TreeItem
          key={i}
          node={child}
          depth={depth + 1}
          selected={false}
          onSelect={onSelect}
        />
      ))}
    </Box>
  );
}

export function FileTree({ tree }: Props) {
  return (
    <Box flexDirection="column" borderStyle="single" borderColor="gray" paddingX={1}>
      <Text bold color="cyan">Project Files</Text>
      {tree.map((node, i) => (
        <TreeItem key={i} node={node} depth={0} selected={false} />
      ))}
    </Box>
  );
}
