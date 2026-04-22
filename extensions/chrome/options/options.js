// Code Agents — Options Page Logic

(async () => {
  const serverUrlInput = document.getElementById('server-url');
  const defaultAgentSelect = document.getElementById('default-agent');
  const themeToggle = document.getElementById('theme-toggle');
  const btnSave = document.getElementById('btn-save');
  const saveStatus = document.getElementById('save-status');

  // Populate agent dropdown
  for (const agent of AGENTS) {
    const opt = document.createElement('option');
    opt.value = agent.name;
    opt.textContent = agentLabel(agent);
    defaultAgentSelect.appendChild(opt);
  }

  // Load current settings
  try {
    const data = await chrome.storage.sync.get(['serverUrl', 'defaultAgent', 'theme']);
    serverUrlInput.value = data.serverUrl || 'http://localhost:8000';
    if (data.defaultAgent) defaultAgentSelect.value = data.defaultAgent;
    if (data.theme) themeToggle.value = data.theme;
  } catch { /* defaults are fine */ }

  // Save
  btnSave.addEventListener('click', async () => {
    const settings = {
      serverUrl: serverUrlInput.value.replace(/\/+$/, '') || 'http://localhost:8000',
      defaultAgent: defaultAgentSelect.value,
      theme: themeToggle.value,
    };

    await chrome.storage.sync.set(settings);

    saveStatus.textContent = 'Saved!';
    setTimeout(() => { saveStatus.textContent = ''; }, 2000);
  });
})();
