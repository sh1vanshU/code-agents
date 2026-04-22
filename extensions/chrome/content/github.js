// Code Agents — GitHub Content Script
// Extracts context from GitHub PR, Issue, and Code pages

(() => {
  const url = window.location.pathname;

  function extractText(selector) {
    const el = document.querySelector(selector);
    return el ? el.textContent.trim() : '';
  }

  function extractAllText(selector) {
    return Array.from(document.querySelectorAll(selector))
      .map((el) => el.textContent.trim())
      .filter(Boolean);
  }

  function detectPageType() {
    if (/\/pull\/\d+/.test(url)) return 'pr';
    if (/\/issues\/\d+/.test(url)) return 'issue';
    if (/\/blob\//.test(url)) return 'code';
    return null;
  }

  function extractPRContext() {
    const title = extractText('.js-issue-title') ||
                  extractText('[data-testid="issue-title"]') ||
                  extractText('.gh-header-title .markdown-title');

    const description = extractText('.comment-body') ||
                        extractText('.markdown-body');

    const files = extractAllText('.file-header .file-info a, .file-header [title]')
      .slice(0, 20) // cap at 20 files
      .join(', ');

    const labels = extractAllText('.js-issue-labels .IssueLabel, .sidebar-labels .IssueLabel')
      .join(', ');

    return { type: 'pr', title, description: truncate(description, 500), files, labels };
  }

  function extractIssueContext() {
    const title = extractText('.js-issue-title') ||
                  extractText('[data-testid="issue-title"]') ||
                  extractText('.gh-header-title .markdown-title');

    const body = extractText('.comment-body') ||
                 extractText('.markdown-body');

    const labels = extractAllText('.js-issue-labels .IssueLabel, .sidebar-labels .IssueLabel')
      .join(', ');

    return { type: 'issue', title, description: truncate(body, 500), labels };
  }

  function extractCodeContext() {
    const filePath = extractText('#file-name-id-wide') ||
                     extractText('.final-path') ||
                     extractText('[data-testid="breadcrumbs-filename"]') ||
                     url.replace(/^.*\/blob\/[^/]+\//, '');

    // Get visible code (first ~50 lines)
    const codeLines = extractAllText('.blob-code-inner, .react-code-line-contents')
      .slice(0, 50);

    return {
      type: 'code',
      title: filePath,
      description: truncate(codeLines.join('\n'), 800),
    };
  }

  function truncate(text, max) {
    if (!text || text.length <= max) return text || '';
    return text.slice(0, max) + '...';
  }

  // ---- Main ----
  const pageType = detectPageType();
  if (!pageType) return; // not a page we care about

  let data;
  switch (pageType) {
    case 'pr':    data = extractPRContext(); break;
    case 'issue': data = extractIssueContext(); break;
    case 'code':  data = extractCodeContext(); break;
    default:      return;
  }

  // Only send if we extracted something meaningful
  if (!data.title && !data.description) return;

  chrome.runtime.sendMessage({
    type: 'page-context',
    source: 'github',
    data,
  }).catch(() => {
    // Extension context may be invalid; ignore
  });
})();
