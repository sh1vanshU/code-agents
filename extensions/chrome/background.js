// Code Agents — Background Service Worker (Manifest V3)

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'ask-code-agents',
    title: 'Ask Code Agents about this',
    contexts: ['selection'],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== 'ask-code-agents') return;

  const selectedText = info.selectionText || '';
  if (!selectedText.trim()) return;

  // Store the context so the side panel can pick it up when it opens
  await chrome.storage.session.set({
    pendingContext: {
      type: 'selected-text',
      text: selectedText,
      url: tab?.url || '',
      title: tab?.title || '',
      timestamp: Date.now(),
    },
  });

  // Open the side panel on the current tab
  try {
    await chrome.sidePanel.open({ tabId: tab.id });
  } catch (err) {
    console.error('Failed to open side panel:', err);
  }
});

// Relay page-context messages from content scripts to the side panel
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'page-context') {
    // Store for the side panel to consume
    chrome.storage.session.set({
      pendingContext: {
        ...message,
        timestamp: Date.now(),
      },
    });
    sendResponse({ ok: true });
  }
  // Return false — we responded synchronously
  return false;
});
