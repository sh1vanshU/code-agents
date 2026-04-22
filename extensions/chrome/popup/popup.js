// Code Agents — Popup Logic

(async () => {
  const statusLabel = document.getElementById('status-label');
  const agentSelect = document.getElementById('agent-select');
  const btnOpenPanel = document.getElementById('btn-open-panel');
  const linkSettings = document.getElementById('link-settings');

  // Load settings
  let serverUrl = 'http://localhost:8000';
  let currentAgent = DEFAULT_AGENT;

  try {
    const data = await chrome.storage.sync.get(['serverUrl', 'defaultAgent']);
    if (data.serverUrl) serverUrl = data.serverUrl;
    if (data.defaultAgent) currentAgent = data.defaultAgent;
  } catch { /* defaults */ }

  // Populate agent selector
  for (const agent of AGENTS) {
    const opt = document.createElement('option');
    opt.value = agent.name;
    opt.textContent = agentLabel(agent);
    if (agent.name === currentAgent) opt.selected = true;
    agentSelect.appendChild(opt);
  }

  // Check server status
  const connected = await checkServer(serverUrl);
  statusLabel.textContent = connected ? 'Connected' : 'Disconnected';
  statusLabel.classList.toggle('connected', connected);
  statusLabel.classList.toggle('disconnected', !connected);

  // Agent change
  agentSelect.addEventListener('change', () => {
    chrome.storage.sync.set({ defaultAgent: agentSelect.value });
  });

  // Open side panel
  btnOpenPanel.addEventListener('click', async () => {
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab) {
        await chrome.sidePanel.open({ tabId: tab.id });
      }
    } catch (err) {
      console.error('Failed to open side panel:', err);
    }
    window.close();
  });

  // Settings link
  linkSettings.addEventListener('click', (e) => {
    e.preventDefault();
    chrome.runtime.openOptionsPage();
    window.close();
  });
})();
