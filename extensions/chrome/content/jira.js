// Code Agents — Jira Content Script
// Extracts context from Jira ticket pages on *.atlassian.net

(() => {
  const url = window.location.href;

  // Only activate on ticket pages
  if (!/\/(browse|issue)\/[A-Z]+-\d+/.test(url)) return;

  function extractText(selector) {
    const el = document.querySelector(selector);
    return el ? el.textContent.trim() : '';
  }

  // Wait briefly for Jira SPA to render content
  function waitForElement(selector, timeout = 3000) {
    return new Promise((resolve) => {
      const el = document.querySelector(selector);
      if (el) return resolve(el);

      const observer = new MutationObserver(() => {
        const found = document.querySelector(selector);
        if (found) { observer.disconnect(); resolve(found); }
      });
      observer.observe(document.body, { childList: true, subtree: true });
      setTimeout(() => { observer.disconnect(); resolve(null); }, timeout);
    });
  }

  async function extractJiraContext() {
    // Wait for the summary heading to appear (Jira is a SPA)
    await waitForElement('[data-testid="issue.views.issue-base.foundation.summary.heading"]', 4000);

    const summary =
      extractText('[data-testid="issue.views.issue-base.foundation.summary.heading"]') ||
      extractText('#summary-val') ||
      extractText('h1');

    const description =
      extractText('[data-testid="issue.views.field.rich-text.description"] .ak-renderer-document') ||
      extractText('#description-val .user-content-block') ||
      extractText('[data-testid="issue-description"]');

    const status =
      extractText('[data-testid="issue.views.issue-base.foundation.status.status-field-wrapper"] button') ||
      extractText('#status-val .jira-issue-status-lozenge') ||
      extractText('[data-testid="issue-status"]');

    const priority =
      extractText('[data-testid="issue.views.field.priority.common.ui.inline-edit--read-view"]') ||
      extractText('#priority-val') ||
      '';

    // Extract ticket key from URL
    const keyMatch = url.match(/\/(browse|issue)\/([A-Z]+-\d+)/);
    const ticketKey = keyMatch ? keyMatch[2] : '';

    return {
      type: 'ticket',
      key: ticketKey,
      title: summary,
      description: truncate(description, 600),
      status,
      priority,
    };
  }

  function truncate(text, max) {
    if (!text || text.length <= max) return text || '';
    return text.slice(0, max) + '...';
  }

  extractJiraContext().then((data) => {
    if (!data.title && !data.description) return;

    chrome.runtime.sendMessage({
      type: 'page-context',
      source: 'jira',
      data,
    }).catch(() => {
      // Extension context invalid; ignore
    });
  });
})();
