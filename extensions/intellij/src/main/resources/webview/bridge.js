// Code Agents — IDE Bridge Adapter
// Detects the IDE environment and provides a unified window.IDE API.
// This file is loaded by the JCEF bridge after page load in IntelliJ.
// In VS Code, the webview's own api.ts handles detection.

(function() {
  'use strict';

  // If IDE already exists (set by JcefBridge.kt), ensure callbacks work
  if (window.IDE && window.IDE.platform === 'intellij') {
    console.log('[CodeAgents] IDE bridge ready (IntelliJ/JCEF)');
    return;
  }

  // Fallback: if loaded standalone in a browser for testing
  if (!window.IDE) {
    window.IDE = {
      postMessage: function(msg) { console.log('[IDE.postMessage]', msg); },
      onMessage: function(cb) { window._ideCallback = cb; },
      getState: function() {
        try { return JSON.parse(localStorage.getItem('ca-state') || '{}'); }
        catch(e) { return {}; }
      },
      setState: function(s) {
        try { localStorage.setItem('ca-state', JSON.stringify(s)); }
        catch(e) {}
      },
      platform: 'browser'
    };
    console.log('[CodeAgents] IDE bridge ready (browser fallback)');
  }
})();
