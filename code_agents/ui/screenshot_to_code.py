"""Screenshot-to-Code — paste a screenshot/mockup, generate matching UI code.

Template-based generation for common UI patterns (login form, dashboard, data table,
card grid, nav sidebar, modal dialog). Detects project framework from package.json
or file structure. No external AI call needed for basic patterns.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.ui.screenshot_to_code")


@dataclass
class UIComponent:
    """A detected UI component in the generated output."""

    name: str
    type: str  # "button", "form", "card", "table", "nav", "modal"
    properties: dict = field(default_factory=dict)


@dataclass
class GeneratedUI:
    """Result of screenshot-to-code generation."""

    framework: str
    code: str
    components: list[UIComponent] = field(default_factory=list)
    preview_html: str = ""
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Template library for common UI patterns
# ---------------------------------------------------------------------------

TEMPLATES: dict[str, dict[str, str]] = {
    "login_form": {
        "description": "Login form with email/password fields and submit button",
        "keywords": ["login", "sign in", "signin", "auth", "email", "password"],
    },
    "dashboard": {
        "description": "Dashboard with stat cards, chart area, and recent activity",
        "keywords": ["dashboard", "stats", "analytics", "overview", "metrics"],
    },
    "data_table": {
        "description": "Data table with headers, rows, sorting, and pagination",
        "keywords": ["table", "data", "list", "grid", "rows", "columns", "pagination"],
    },
    "card_grid": {
        "description": "Responsive card grid layout",
        "keywords": ["card", "grid", "tiles", "gallery", "product", "items"],
    },
    "nav_sidebar": {
        "description": "Navigation sidebar with links and collapsible sections",
        "keywords": ["sidebar", "nav", "navigation", "menu", "drawer"],
    },
    "modal_dialog": {
        "description": "Modal dialog with header, body, and action buttons",
        "keywords": ["modal", "dialog", "popup", "overlay", "confirm"],
    },
}


def _match_template(description: str) -> Optional[str]:
    """Match a description to the best template by keyword overlap."""
    if not description:
        return None
    desc_lower = description.lower()
    best_match = None
    best_score = 0
    for name, info in TEMPLATES.items():
        score = sum(1 for kw in info["keywords"] if kw in desc_lower)
        if score > best_score:
            best_score = score
            best_match = name
    return best_match if best_score > 0 else None


# ---------------------------------------------------------------------------
# HTML templates
# ---------------------------------------------------------------------------

_HTML_LOGIN_FORM = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Login</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         display: flex; justify-content: center; align-items: center;
         min-height: 100vh; background: #f5f5f5; }
  .login-card { background: #fff; padding: 2rem; border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1); width: 100%; max-width: 400px; }
  .login-card h2 { margin-bottom: 1.5rem; text-align: center; color: #333; }
  .form-group { margin-bottom: 1rem; }
  .form-group label { display: block; margin-bottom: 0.25rem; font-size: 0.875rem; color: #555; }
  .form-group input { width: 100%; padding: 0.75rem; border: 1px solid #ddd;
                      border-radius: 4px; font-size: 1rem; }
  .form-group input:focus { outline: none; border-color: #4a90d9; box-shadow: 0 0 0 2px rgba(74,144,217,0.2); }
  .btn-primary { width: 100%; padding: 0.75rem; background: #4a90d9; color: #fff;
                 border: none; border-radius: 4px; font-size: 1rem; cursor: pointer; }
  .btn-primary:hover { background: #357abd; }
  .links { text-align: center; margin-top: 1rem; font-size: 0.875rem; }
  .links a { color: #4a90d9; text-decoration: none; }
</style>
</head>
<body>
<div class="login-card">
  <h2>Sign In</h2>
  <form>
    <div class="form-group">
      <label for="email">Email</label>
      <input type="email" id="email" name="email" placeholder="you@example.com" required>
    </div>
    <div class="form-group">
      <label for="password">Password</label>
      <input type="password" id="password" name="password" placeholder="Password" required>
    </div>
    <button type="submit" class="btn-primary">Sign In</button>
  </form>
  <div class="links"><a href="#">Forgot password?</a></div>
</div>
</body>
</html>"""

_HTML_DASHBOARD = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; }
  .header { background: #fff; padding: 1rem 2rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .header h1 { font-size: 1.25rem; color: #333; }
  .container { max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
  .stat-card { background: #fff; padding: 1.5rem; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  .stat-card .label { font-size: 0.875rem; color: #888; margin-bottom: 0.5rem; }
  .stat-card .value { font-size: 1.75rem; font-weight: 600; color: #333; }
  .panels { display: grid; grid-template-columns: 2fr 1fr; gap: 1rem; }
  .panel { background: #fff; padding: 1.5rem; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  .panel h3 { margin-bottom: 1rem; color: #333; font-size: 1rem; }
  .chart-placeholder { height: 200px; background: #f9f9f9; border: 2px dashed #ddd;
                       border-radius: 4px; display: flex; align-items: center;
                       justify-content: center; color: #aaa; }
  .activity-item { padding: 0.75rem 0; border-bottom: 1px solid #f0f0f0; font-size: 0.875rem; color: #555; }
  .activity-item:last-child { border-bottom: none; }
</style>
</head>
<body>
<div class="header"><h1>Dashboard</h1></div>
<div class="container">
  <div class="stats">
    <div class="stat-card"><div class="label">Total Users</div><div class="value">12,845</div></div>
    <div class="stat-card"><div class="label">Revenue</div><div class="value">$48.2K</div></div>
    <div class="stat-card"><div class="label">Orders</div><div class="value">1,234</div></div>
    <div class="stat-card"><div class="label">Conversion</div><div class="value">3.2%</div></div>
  </div>
  <div class="panels">
    <div class="panel">
      <h3>Revenue Over Time</h3>
      <div class="chart-placeholder">Chart goes here</div>
    </div>
    <div class="panel">
      <h3>Recent Activity</h3>
      <div class="activity-item">New user signup — 2 min ago</div>
      <div class="activity-item">Order #1234 placed — 5 min ago</div>
      <div class="activity-item">Payment received — 12 min ago</div>
      <div class="activity-item">Support ticket #89 resolved — 1h ago</div>
    </div>
  </div>
</div>
</body>
</html>"""

_HTML_DATA_TABLE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Data Table</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #f5f5f5; padding: 2rem; }
  .table-container { background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                     overflow: hidden; max-width: 900px; margin: 0 auto; }
  .table-header { padding: 1rem 1.5rem; display: flex; justify-content: space-between; align-items: center; }
  .table-header h2 { font-size: 1.125rem; color: #333; }
  .search-input { padding: 0.5rem 0.75rem; border: 1px solid #ddd; border-radius: 4px; font-size: 0.875rem; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; padding: 0.75rem 1.5rem; background: #fafafa; color: #888;
       font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid #eee; }
  td { padding: 0.75rem 1.5rem; border-bottom: 1px solid #f0f0f0; font-size: 0.875rem; color: #555; }
  tr:hover td { background: #f9f9f9; }
  .pagination { padding: 1rem 1.5rem; display: flex; justify-content: space-between;
                align-items: center; font-size: 0.875rem; color: #888; }
  .pagination button { padding: 0.4rem 0.75rem; border: 1px solid #ddd; background: #fff;
                       border-radius: 4px; cursor: pointer; font-size: 0.8rem; }
  .pagination button:hover { background: #f5f5f5; }
</style>
</head>
<body>
<div class="table-container">
  <div class="table-header">
    <h2>Users</h2>
    <input class="search-input" type="text" placeholder="Search...">
  </div>
  <table>
    <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th></tr></thead>
    <tbody>
      <tr><td>Alice Johnson</td><td>alice@example.com</td><td>Admin</td><td>Active</td></tr>
      <tr><td>Bob Smith</td><td>bob@example.com</td><td>Editor</td><td>Active</td></tr>
      <tr><td>Carol White</td><td>carol@example.com</td><td>Viewer</td><td>Inactive</td></tr>
    </tbody>
  </table>
  <div class="pagination">
    <span>Showing 1-3 of 42</span>
    <div><button>Prev</button> <button>Next</button></div>
  </div>
</div>
</body>
</html>"""

_HTML_CARD_GRID = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Card Grid</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #f5f5f5; padding: 2rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 1.5rem; max-width: 1200px; margin: 0 auto; }
  .card { background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; }
  .card-image { height: 180px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                display: flex; align-items: center; justify-content: center; color: #fff; font-size: 2rem; }
  .card-body { padding: 1.25rem; }
  .card-body h3 { font-size: 1rem; color: #333; margin-bottom: 0.5rem; }
  .card-body p { font-size: 0.875rem; color: #777; line-height: 1.5; margin-bottom: 1rem; }
  .card-body .btn { display: inline-block; padding: 0.5rem 1rem; background: #4a90d9; color: #fff;
                    border-radius: 4px; text-decoration: none; font-size: 0.8rem; }
  .card-body .btn:hover { background: #357abd; }
</style>
</head>
<body>
<div class="grid">
  <div class="card">
    <div class="card-image">1</div>
    <div class="card-body">
      <h3>Card Title</h3>
      <p>Brief description of the item with enough text to show layout.</p>
      <a href="#" class="btn">View Details</a>
    </div>
  </div>
  <div class="card">
    <div class="card-image">2</div>
    <div class="card-body">
      <h3>Card Title</h3>
      <p>Brief description of the item with enough text to show layout.</p>
      <a href="#" class="btn">View Details</a>
    </div>
  </div>
  <div class="card">
    <div class="card-image">3</div>
    <div class="card-body">
      <h3>Card Title</h3>
      <p>Brief description of the item with enough text to show layout.</p>
      <a href="#" class="btn">View Details</a>
    </div>
  </div>
</div>
</body>
</html>"""

_HTML_NAV_SIDEBAR = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sidebar Navigation</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; display: flex; min-height: 100vh; }
  .sidebar { width: 260px; background: #1a1a2e; color: #fff; padding: 1.5rem 0; flex-shrink: 0; }
  .sidebar .logo { padding: 0 1.5rem 1.5rem; font-size: 1.25rem; font-weight: 600; border-bottom: 1px solid rgba(255,255,255,0.1); }
  .nav-section { padding: 1rem 0; }
  .nav-section .section-title { padding: 0.5rem 1.5rem; font-size: 0.7rem; text-transform: uppercase;
                                 letter-spacing: 1px; color: rgba(255,255,255,0.4); }
  .nav-item { display: flex; align-items: center; padding: 0.6rem 1.5rem; color: rgba(255,255,255,0.7);
              text-decoration: none; font-size: 0.875rem; transition: background 0.2s; }
  .nav-item:hover { background: rgba(255,255,255,0.05); color: #fff; }
  .nav-item.active { background: rgba(74,144,217,0.2); color: #4a90d9; border-right: 3px solid #4a90d9; }
  .main { flex: 1; background: #f5f5f5; padding: 2rem; }
  .main h1 { color: #333; font-size: 1.5rem; }
</style>
</head>
<body>
<div class="sidebar">
  <div class="logo">AppName</div>
  <div class="nav-section">
    <div class="section-title">Main</div>
    <a href="#" class="nav-item active">Dashboard</a>
    <a href="#" class="nav-item">Analytics</a>
    <a href="#" class="nav-item">Reports</a>
  </div>
  <div class="nav-section">
    <div class="section-title">Management</div>
    <a href="#" class="nav-item">Users</a>
    <a href="#" class="nav-item">Settings</a>
    <a href="#" class="nav-item">Integrations</a>
  </div>
</div>
<div class="main"><h1>Page Content</h1></div>
</body>
</html>"""

_HTML_MODAL_DIALOG = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Modal Dialog</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         display: flex; justify-content: center; align-items: center; min-height: 100vh;
         background: rgba(0,0,0,0.5); }
  .modal { background: #fff; border-radius: 12px; box-shadow: 0 20px 60px rgba(0,0,0,0.3);
           width: 100%; max-width: 480px; overflow: hidden; }
  .modal-header { padding: 1.25rem 1.5rem; border-bottom: 1px solid #eee;
                  display: flex; justify-content: space-between; align-items: center; }
  .modal-header h3 { font-size: 1.125rem; color: #333; }
  .modal-close { background: none; border: none; font-size: 1.5rem; color: #999; cursor: pointer; }
  .modal-body { padding: 1.5rem; font-size: 0.9rem; color: #555; line-height: 1.6; }
  .modal-footer { padding: 1rem 1.5rem; border-top: 1px solid #eee; display: flex;
                  justify-content: flex-end; gap: 0.75rem; }
  .btn { padding: 0.6rem 1.25rem; border-radius: 6px; font-size: 0.875rem; cursor: pointer; border: none; }
  .btn-cancel { background: #f0f0f0; color: #555; }
  .btn-cancel:hover { background: #e0e0e0; }
  .btn-confirm { background: #4a90d9; color: #fff; }
  .btn-confirm:hover { background: #357abd; }
</style>
</head>
<body>
<div class="modal">
  <div class="modal-header">
    <h3>Confirm Action</h3>
    <button class="modal-close">&times;</button>
  </div>
  <div class="modal-body">
    Are you sure you want to proceed? This action cannot be undone.
  </div>
  <div class="modal-footer">
    <button class="btn btn-cancel">Cancel</button>
    <button class="btn btn-confirm">Confirm</button>
  </div>
</div>
</body>
</html>"""

_HTML_TEMPLATES: dict[str, str] = {
    "login_form": _HTML_LOGIN_FORM,
    "dashboard": _HTML_DASHBOARD,
    "data_table": _HTML_DATA_TABLE,
    "card_grid": _HTML_CARD_GRID,
    "nav_sidebar": _HTML_NAV_SIDEBAR,
    "modal_dialog": _HTML_MODAL_DIALOG,
}

# ---------------------------------------------------------------------------
# React templates
# ---------------------------------------------------------------------------

_REACT_TEMPLATES: dict[str, str] = {
    "login_form": """\
import React, { useState } from 'react';

export default function LoginForm() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    console.log('Login:', { email, password });
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f5f5f5' }}>
      <div style={{ background: '#fff', padding: '2rem', borderRadius: '8px', boxShadow: '0 2px 10px rgba(0,0,0,0.1)', width: '100%', maxWidth: '400px' }}>
        <h2 style={{ textAlign: 'center', marginBottom: '1.5rem', color: '#333' }}>Sign In</h2>
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', marginBottom: '0.25rem', fontSize: '0.875rem', color: '#555' }}>Email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
              style={{ width: '100%', padding: '0.75rem', border: '1px solid #ddd', borderRadius: '4px', fontSize: '1rem' }}
              placeholder="you@example.com" required />
          </div>
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', marginBottom: '0.25rem', fontSize: '0.875rem', color: '#555' }}>Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              style={{ width: '100%', padding: '0.75rem', border: '1px solid #ddd', borderRadius: '4px', fontSize: '1rem' }}
              placeholder="Password" required />
          </div>
          <button type="submit" style={{ width: '100%', padding: '0.75rem', background: '#4a90d9', color: '#fff', border: 'none', borderRadius: '4px', fontSize: '1rem', cursor: 'pointer' }}>
            Sign In
          </button>
        </form>
      </div>
    </div>
  );
}""",
    "dashboard": """\
import React from 'react';

const stats = [
  { label: 'Total Users', value: '12,845' },
  { label: 'Revenue', value: '$48.2K' },
  { label: 'Orders', value: '1,234' },
  { label: 'Conversion', value: '3.2%' },
];

export default function Dashboard() {
  return (
    <div style={{ fontFamily: '-apple-system, BlinkMacSystemFont, sans-serif', background: '#f0f2f5', minHeight: '100vh' }}>
      <header style={{ background: '#fff', padding: '1rem 2rem', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
        <h1 style={{ fontSize: '1.25rem', color: '#333' }}>Dashboard</h1>
      </header>
      <div style={{ maxWidth: '1200px', margin: '2rem auto', padding: '0 1rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
          {stats.map((s) => (
            <div key={s.label} style={{ background: '#fff', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
              <div style={{ fontSize: '0.875rem', color: '#888', marginBottom: '0.5rem' }}>{s.label}</div>
              <div style={{ fontSize: '1.75rem', fontWeight: 600, color: '#333' }}>{s.value}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}""",
    "data_table": """\
import React, { useState } from 'react';

const data = [
  { name: 'Alice Johnson', email: 'alice@example.com', role: 'Admin', status: 'Active' },
  { name: 'Bob Smith', email: 'bob@example.com', role: 'Editor', status: 'Active' },
  { name: 'Carol White', email: 'carol@example.com', role: 'Viewer', status: 'Inactive' },
];

export default function DataTable() {
  const [search, setSearch] = useState('');
  const filtered = data.filter((r) => r.name.toLowerCase().includes(search.toLowerCase()));

  return (
    <div style={{ background: '#fff', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', overflow: 'hidden', maxWidth: '900px', margin: '2rem auto' }}>
      <div style={{ padding: '1rem 1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ fontSize: '1.125rem', color: '#333' }}>Users</h2>
        <input value={search} onChange={(e) => setSearch(e.target.value)}
          style={{ padding: '0.5rem 0.75rem', border: '1px solid #ddd', borderRadius: '4px', fontSize: '0.875rem' }}
          placeholder="Search..." />
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>{['Name','Email','Role','Status'].map((h) => (
            <th key={h} style={{ textAlign: 'left', padding: '0.75rem 1.5rem', background: '#fafafa', color: '#888', fontSize: '0.75rem', textTransform: 'uppercase', borderBottom: '1px solid #eee' }}>{h}</th>
          ))}</tr>
        </thead>
        <tbody>
          {filtered.map((r) => (
            <tr key={r.email}>
              <td style={{ padding: '0.75rem 1.5rem', borderBottom: '1px solid #f0f0f0', fontSize: '0.875rem', color: '#555' }}>{r.name}</td>
              <td style={{ padding: '0.75rem 1.5rem', borderBottom: '1px solid #f0f0f0', fontSize: '0.875rem', color: '#555' }}>{r.email}</td>
              <td style={{ padding: '0.75rem 1.5rem', borderBottom: '1px solid #f0f0f0', fontSize: '0.875rem', color: '#555' }}>{r.role}</td>
              <td style={{ padding: '0.75rem 1.5rem', borderBottom: '1px solid #f0f0f0', fontSize: '0.875rem', color: '#555' }}>{r.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}""",
}

# ---------------------------------------------------------------------------
# Vue templates
# ---------------------------------------------------------------------------

_VUE_TEMPLATES: dict[str, str] = {
    "login_form": """\
<template>
  <div class="login-wrapper">
    <div class="login-card">
      <h2>Sign In</h2>
      <form @submit.prevent="handleSubmit">
        <div class="form-group">
          <label for="email">Email</label>
          <input v-model="email" type="email" id="email" placeholder="you@example.com" required />
        </div>
        <div class="form-group">
          <label for="password">Password</label>
          <input v-model="password" type="password" id="password" placeholder="Password" required />
        </div>
        <button type="submit" class="btn-primary">Sign In</button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
const email = ref('');
const password = ref('');
const handleSubmit = () => console.log('Login:', { email: email.value, password: password.value });
</script>

<style scoped>
.login-wrapper { display: flex; justify-content: center; align-items: center; min-height: 100vh; background: #f5f5f5; }
.login-card { background: #fff; padding: 2rem; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); width: 100%; max-width: 400px; }
.login-card h2 { text-align: center; margin-bottom: 1.5rem; color: #333; }
.form-group { margin-bottom: 1rem; }
.form-group label { display: block; margin-bottom: 0.25rem; font-size: 0.875rem; color: #555; }
.form-group input { width: 100%; padding: 0.75rem; border: 1px solid #ddd; border-radius: 4px; font-size: 1rem; }
.btn-primary { width: 100%; padding: 0.75rem; background: #4a90d9; color: #fff; border: none; border-radius: 4px; font-size: 1rem; cursor: pointer; }
</style>""",
}


# ---------------------------------------------------------------------------
# ScreenshotToCode class
# ---------------------------------------------------------------------------

class ScreenshotToCode:
    """Generate UI code from a screenshot or description."""

    SUPPORTED_FRAMEWORKS = ("html", "react", "vue")

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("ScreenshotToCode initialized, cwd=%s", cwd)

    def generate(
        self,
        image_path: str = "",
        framework: str = "",
        description: str = "",
    ) -> GeneratedUI:
        """Generate UI code from an image path or text description.

        1. Read image file (for metadata / filename hints)
        2. If no framework specified, detect from project files
        3. Analyze image description (or use provided description)
        4. Generate UI code matching the screenshot
        """
        warnings: list[str] = []

        # Resolve framework
        if not framework:
            framework = self._detect_framework()
            logger.info("Auto-detected framework: %s", framework)

        framework = framework.lower().strip()
        if framework not in self.SUPPORTED_FRAMEWORKS:
            warnings.append(f"Unsupported framework '{framework}', falling back to html")
            framework = "html"

        # Build description from image path hints if no description given
        if not description and image_path:
            description = self._analyze_image(image_path)

        if not description:
            description = "dashboard"
            warnings.append("No description provided, defaulting to dashboard template")

        # Match to template
        template_name = _match_template(description)
        if not template_name:
            template_name = "dashboard"
            warnings.append(f"Could not match description to a template, using dashboard")

        logger.info("Generating %s code for template '%s'", framework, template_name)

        # Generate code for the chosen framework
        if framework == "react":
            code = self._generate_react(template_name)
        elif framework == "vue":
            code = self._generate_vue(template_name)
        else:
            code = self._generate_html(template_name)

        components = self._extract_components(code)
        preview = self._generate_preview(code, framework)

        return GeneratedUI(
            framework=framework,
            code=code,
            components=components,
            preview_html=preview,
            warnings=warnings,
        )

    def _detect_framework(self) -> str:
        """Detect frontend framework from project files."""
        pkg_json = Path(self.cwd) / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text())
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                if "react" in deps or "react-dom" in deps or "next" in deps:
                    return "react"
                if "vue" in deps or "nuxt" in deps:
                    return "vue"
                if "@angular/core" in deps:
                    return "html"  # Angular not yet templated, fall back
                if "svelte" in deps:
                    return "html"  # Svelte not yet templated, fall back
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to parse package.json: %s", exc)

        # Check for common framework files
        cwd_path = Path(self.cwd)
        if list(cwd_path.glob("*.jsx")) or list(cwd_path.glob("*.tsx")):
            return "react"
        if list(cwd_path.glob("*.vue")):
            return "vue"

        return "html"

    def _analyze_image(self, image_path: str) -> str:
        """Extract hints from image path / filename for template matching."""
        p = Path(image_path)
        if not p.exists():
            logger.warning("Image file not found: %s", image_path)
            return ""

        # Use filename as description hint
        stem = p.stem.lower().replace("-", " ").replace("_", " ")
        logger.debug("Image filename hint: %s", stem)
        return stem

    def _generate_html(self, template_name: str) -> str:
        """Return HTML template for the given pattern."""
        return _HTML_TEMPLATES.get(template_name, _HTML_TEMPLATES["dashboard"])

    def _generate_react(self, template_name: str) -> str:
        """Return React JSX template for the given pattern."""
        if template_name in _REACT_TEMPLATES:
            return _REACT_TEMPLATES[template_name]
        # Fall back to login_form as a generic react component
        return _REACT_TEMPLATES.get("login_form", "// No React template available")

    def _generate_vue(self, template_name: str) -> str:
        """Return Vue SFC template for the given pattern."""
        if template_name in _VUE_TEMPLATES:
            return _VUE_TEMPLATES[template_name]
        return _VUE_TEMPLATES.get("login_form", "<!-- No Vue template available -->")

    def _extract_components(self, code: str) -> list[UIComponent]:
        """Parse generated code to identify UI components."""
        components: list[UIComponent] = []

        # Detect buttons
        button_pattern = re.compile(r'<button[^>]*>(.*?)</button>', re.DOTALL | re.IGNORECASE)
        for match in button_pattern.finditer(code):
            text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
            components.append(UIComponent(
                name=text or "Button",
                type="button",
                properties={"text": text},
            ))

        # Detect forms
        if re.search(r'<form', code, re.IGNORECASE):
            inputs = re.findall(r'<input[^>]*type=["\'](\w+)["\']', code, re.IGNORECASE)
            components.append(UIComponent(
                name="Form",
                type="form",
                properties={"fields": inputs},
            ))

        # Detect tables
        if re.search(r'<table', code, re.IGNORECASE):
            headers = re.findall(r'<th[^>]*>(.*?)</th>', code, re.IGNORECASE)
            components.append(UIComponent(
                name="DataTable",
                type="table",
                properties={"columns": [re.sub(r'<[^>]+>', '', h).strip() for h in headers]},
            ))

        # Detect cards
        card_count = len(re.findall(r'class=["\'][^"\']*card[^"\']*["\']', code, re.IGNORECASE))
        if card_count > 0:
            components.append(UIComponent(
                name="CardGrid",
                type="card",
                properties={"count": card_count},
            ))

        # Detect navigation
        if re.search(r'class=["\'][^"\']*(?:nav|sidebar)[^"\']*["\']', code, re.IGNORECASE):
            nav_items = re.findall(r'<a[^>]*class=["\'][^"\']*nav-item[^"\']*["\'][^>]*>(.*?)</a>', code, re.IGNORECASE)
            components.append(UIComponent(
                name="Navigation",
                type="nav",
                properties={"items": [re.sub(r'<[^>]+>', '', i).strip() for i in nav_items]},
            ))

        # Detect modals
        if re.search(r'class=["\'][^"\']*modal[^"\']*["\']', code, re.IGNORECASE):
            components.append(UIComponent(
                name="Modal",
                type="modal",
                properties={},
            ))

        return components

    def _generate_preview(self, code: str, framework: str) -> str:
        """Wrap generated code in minimal HTML for browser preview."""
        if framework == "html":
            return code  # Already a full HTML document

        # For React/Vue, wrap in a basic HTML shell
        return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Preview — {framework}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         margin: 2rem; background: #f5f5f5; }}
  pre {{ background: #1e1e1e; color: #d4d4d4; padding: 1.5rem; border-radius: 8px;
        overflow-x: auto; font-size: 0.85rem; line-height: 1.5; }}
</style>
</head>
<body>
<h2>{framework.title()} Component Preview</h2>
<p>Copy the code below into your project:</p>
<pre><code>{code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')}</code></pre>
</body>
</html>"""


def format_generated_ui(result: GeneratedUI) -> str:
    """Format a GeneratedUI result for terminal display."""
    lines = []
    lines.append(f"Framework: {result.framework}")
    lines.append(f"Components: {len(result.components)}")
    for comp in result.components:
        props_str = ", ".join(f"{k}={v}" for k, v in comp.properties.items()) if comp.properties else ""
        lines.append(f"  - {comp.name} ({comp.type}){': ' + props_str if props_str else ''}")
    if result.warnings:
        lines.append("")
        for w in result.warnings:
            lines.append(f"Warning: {w}")
    lines.append("")
    lines.append(result.code)
    return "\n".join(lines)
