# Code Agents — Chrome Extension

## Overview
Chrome extension that adds a code-agents chat sidebar to GitHub, Jira, Confluence, and any webpage.

## Architecture
```
src/
├── manifest.json              # Manifest V3
├── background/
│   └── service-worker.js      # Background service worker
├── sidepanel/
│   ├── sidepanel.html         # Side panel chat UI
│   ├── sidepanel.js           # Chat logic + SSE streaming
│   └── sidepanel.css          # Styling
├── content/
│   ├── github.js              # GitHub PR/issue context extractor
│   ├── jira.js                # Jira ticket context extractor
│   ├── confluence.js          # Confluence page content extractor
│   └── generic.js             # Generic page text selection
├── popup/
│   ├── popup.html             # Quick agent selector + server status
│   └── popup.js
├── options/
│   ├── options.html           # Settings page
│   └── options.js
└── shared/
    ├── api-client.js          # HTTP client for localhost:8000
    ├── sse-reader.js          # SSE stream parser
    └── agents.js              # Agent list + descriptions
```

## Features

### Side Panel Chat
- Full chat interface in Chrome side panel (Chrome 114+)
- Streaming responses via SSE
- Agent selector dropdown
- Message history per tab

### Context-Aware Actions
| Website | Auto-extracted context |
|---------|----------------------|
| **GitHub PR** | Diff, file changes, PR description, comments |
| **GitHub Issue** | Issue body, labels, assignees |
| **Jira Ticket** | Summary, description, acceptance criteria, status |
| **Confluence Page** | Page content, title, space |
| **Any Page** | Selected text via context menu |

### Context Menu
Right-click on any text → "Ask Code Agents" → opens side panel with selected text as context.

### Popup
Quick access:
- Server status (green/red dot)
- Current agent selector
- Recent conversations
- "Open Side Panel" button

## API Integration
All calls to `http://localhost:8000/v1/agents/{agent}/chat/completions`

Requires `host_permissions` for `http://localhost:8000/*` in manifest.json.

## Development
```bash
cd extensions/chrome
# Load unpacked extension in Chrome:
# chrome://extensions → Developer mode → Load unpacked → select this directory
```

## Build
```bash
# Package as .crx or .zip for Chrome Web Store
zip -r code-agents-chrome.zip src/
```

## Permissions
```json
{
  "permissions": ["sidePanel", "contextMenus", "storage", "activeTab"],
  "host_permissions": ["http://localhost:8000/*"],
  "content_scripts": [{
    "matches": ["https://github.com/*", "https://*.atlassian.net/*"],
    "js": ["content/github.js", "content/jira.js"]
  }]
}
```
