// Code Agents — Webview Entry Point

import './styles/theme.css';
import './styles/base.css';
import './styles/animations.css';
import './styles/toolbar.css';
import './styles/chat.css';
import './styles/input.css';
import './styles/overlays.css';
import './styles/plan.css';
import './styles/code-highlight.css';

import { App } from './app';

// Boot the app
document.addEventListener('DOMContentLoaded', () => {
  const root = document.getElementById('app');
  if (root) {
    new App(root);
  }
});
