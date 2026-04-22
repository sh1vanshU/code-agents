// Code Agents — Lightweight Syntax Highlighter
// Zero-dependency: uses regex-based tokenization for common languages.
// Covers 80% of developer use cases without bundling Prism.js (saves 15KB+).

interface TokenRule {
  pattern: RegExp;
  className: string;
}

const COMMON_RULES: TokenRule[] = [
  // Comments (single-line)
  { pattern: /(\/\/.*$|#.*$)/gm, className: 'hl-comment' },
  // Strings (double-quoted, single-quoted, backtick)
  { pattern: /("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)/g, className: 'hl-string' },
  // Numbers
  { pattern: /\b(\d+\.?\d*(?:e[+-]?\d+)?|0x[0-9a-f]+|0b[01]+)\b/gi, className: 'hl-number' },
  // Keywords (common across languages)
  { pattern: /\b(function|const|let|var|if|else|return|import|export|from|class|def|self|async|await|try|catch|finally|throw|new|for|while|do|switch|case|break|continue|in|of|type|interface|enum|struct|impl|fn|pub|mod|use|package|public|private|protected|static|final|void|int|string|boolean|true|false|null|undefined|None|True|False|yield|lambda|raise|except|pass|with|as|is|not|and|or|extends|implements|abstract|override|super|this|val|var|when|companion|object|data|sealed|suspend|lateinit|lazy|open|internal)\b/g, className: 'hl-keyword' },
  // Types (capitalized words that look like types)
  { pattern: /\b([A-Z][a-zA-Z0-9_]*(?:<[^>]*>)?)\b/g, className: 'hl-type' },
  // Function calls
  { pattern: /\b([a-zA-Z_]\w*)\s*\(/g, className: 'hl-function' },
  // Decorators / annotations
  { pattern: /(@\w+)/g, className: 'hl-decorator' },
  // Operators
  { pattern: /(=>|->|&&|\|\||===?|!==?|<=?|>=?|\+=?|-=?|\*=?|\/=?|%=?|\.\.\.|::)/g, className: 'hl-operator' },
];

/**
 * Apply syntax highlighting to a code string.
 * Returns HTML with <span class="hl-*"> tokens.
 * Input must already be HTML-escaped.
 */
export function highlight(code: string, language: string): string {
  if (!code) return code;

  // Skip highlighting for plain text / unknown
  const skip = ['text', 'plain', 'output', 'log', 'diff'];
  if (skip.includes(language.toLowerCase())) return code;

  let result = code;

  // Apply token rules — order matters (later rules can override earlier)
  // We use placeholder markers to avoid nested replacements
  const markers: { start: number; end: number; cls: string }[] = [];

  for (const rule of COMMON_RULES) {
    // Clone regex to prevent cross-call lastIndex corruption
    const pattern = new RegExp(rule.pattern.source, rule.pattern.flags);
    let match;
    while ((match = pattern.exec(code)) !== null) {
      const matchStr = match[1] || match[0];
      const start = match.index + (match[0].indexOf(matchStr));
      markers.push({ start, end: start + matchStr.length, cls: rule.className });
    }
  }

  // Sort markers by start position (later first for replacement)
  markers.sort((a, b) => b.start - a.start);

  // Remove overlapping markers (keep first/outermost)
  const used = new Set<number>();
  const filtered = markers.filter(m => {
    for (let i = m.start; i < m.end; i++) {
      if (used.has(i)) return false;
    }
    for (let i = m.start; i < m.end; i++) {
      used.add(i);
    }
    return true;
  });

  // Apply markers (from end to start to preserve indices)
  filtered.sort((a, b) => b.start - a.start);
  for (const m of filtered) {
    const before = result.slice(0, m.start);
    const content = result.slice(m.start, m.end);
    const after = result.slice(m.end);
    result = `${before}<span class="${m.cls}">${content}</span>${after}`;
  }

  return result;
}
