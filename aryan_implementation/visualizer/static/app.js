/**
 * Real-Time XML Visualizer Frontend Application
 */

let allFiles = [];
let activeFileRel = null;
let activeFileData = null;
let activeTab = 'dashboard';
let sseConnection = null;

document.addEventListener('DOMContentLoaded', () => {
  initSSE();
  loadFiles();
  setupEventListeners();
});

// 1. Server-Sent Events (SSE) for Real-Time Sync
function initSSE() {
  const statusEl = document.getElementById('live-status');
  const textEl = document.getElementById('live-text');

  sseConnection = new EventSource('/api/stream');

  sseConnection.addEventListener('connected', () => {
    statusEl.style.display = 'inline-flex';
    textEl.textContent = 'Live Sync Active';
    statusEl.style.background = 'rgba(16, 185, 129, 0.15)';
    statusEl.style.color = 'var(--success)';
  });

  sseConnection.addEventListener('file_changed', (e) => {
    const data = JSON.parse(e.data);
    console.log('[Live Sync] File changed:', data);

    // Refresh file list metadata
    loadFiles(false);

    // If the changed file is the one currently open, reload its view
    if (activeFileRel && (activeFileRel === data.file || data.file.endsWith(activeFileRel.split('/').pop()))) {
      flashLiveIndicator();
      loadFileContent(activeFileRel, false);
    }
  });

  sseConnection.onerror = () => {
    textEl.textContent = 'Reconnecting...';
    statusEl.style.background = 'rgba(245, 158, 11, 0.15)';
    statusEl.style.color = 'var(--warning)';
  };
}

function flashLiveIndicator() {
  const statusEl = document.getElementById('live-status');
  statusEl.style.background = 'rgba(56, 189, 248, 0.3)';
  setTimeout(() => {
    statusEl.style.background = 'rgba(16, 185, 129, 0.15)';
  }, 1000);
}

// 2. Load & Render File List
async function loadFiles(autoSelect = true) {
  try {
    const res = await fetch('/api/files');
    const data = await res.json();
    allFiles = data.files || [];
    renderFileList(allFiles);

    if (autoSelect && !activeFileRel && allFiles.length > 0) {
      // Prefer ARYAN_IMPLEMENTATION_PLAN.xml if available
      const preferred = allFiles.find(f => f.name === 'ARYAN_IMPLEMENTATION_PLAN.xml') || allFiles[0];
      selectFile(preferred.relpath);
    }
  } catch (err) {
    console.error('Failed to load files:', err);
  }
}

function renderFileList(files) {
  const container = document.getElementById('file-list');
  const searchVal = document.getElementById('search-input').value.toLowerCase();

  const filtered = files.filter(f =>
    f.name.toLowerCase().includes(searchVal) ||
    f.category.toLowerCase().includes(searchVal)
  );

  // Group by category
  const groups = {};
  filtered.forEach(f => {
    groups[f.category] = groups[f.category] || [];
    groups[f.category].push(f);
  });

  let html = '';
  for (const [cat, catFiles] of Object.entries(groups)) {
    html += `<div class="file-category">${escapeHtml(cat)} (${catFiles.length})</div>`;
    catFiles.forEach(f => {
      const isActive = f.relpath === activeFileRel ? 'active' : '';
      const sizeKb = (f.size_bytes / 1024).toFixed(1);
      html += `
        <div class="file-item ${isActive}" onclick="selectFile('${f.relpath}')">
          <div class="file-item-name">${escapeHtml(f.name)}</div>
          <div class="file-item-meta">
            <span>${sizeKb} KB</span>
            <span>${f.relpath.split('/')[0]}</span>
          </div>
        </div>
      `;
    });
  }

  container.innerHTML = html || '<div style="padding: 1rem; color: var(--text-muted);">No XML files matched.</div>';
}

// 3. Select & Load Active File
async function selectFile(relpath) {
  activeFileRel = relpath;
  renderFileList(allFiles);
  await loadFileContent(relpath);
}

async function loadFileContent(relpath, showLoading = true) {
  const contentArea = document.getElementById('content-area');
  if (showLoading) {
    contentArea.innerHTML = '<div style="padding: 2rem; color: var(--text-muted);">Parsing XML and generating visualisations...</div>';
  }

  try {
    const res = await fetch(`/api/xml?file=${encodeURIComponent(relpath)}`);
    const data = await res.json();
    if (!data.ok) {
      contentArea.innerHTML = `<div style="padding: 2rem; color: var(--danger);">Error: ${escapeHtml(data.error)}</div>`;
      return;
    }

    activeFileData = data;
    document.getElementById('current-filename').textContent = data.filename;
    document.getElementById('current-filemeta').textContent = `${data.file_type.toUpperCase()} • ${(data.size_bytes / 1024).toFixed(1)} KB • Root: <${data.root_tag}>`;

    renderActiveTab();
  } catch (err) {
    contentArea.innerHTML = `<div style="padding: 2rem; color: var(--danger);">Failed to fetch XML: ${escapeHtml(err.message)}</div>`;
  }
}

// 4. Tab Management
function setupEventListeners() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeTab = btn.getAttribute('data-tab');
      renderActiveTab();
    });
  });

  document.getElementById('search-input').addEventListener('input', () => {
    renderFileList(allFiles);
  });
}

function renderActiveTab() {
  if (!activeFileData) return;
  const container = document.getElementById('content-area');

  if (activeTab === 'dashboard') {
    container.innerHTML = renderDashboardView(activeFileData);
  } else if (activeTab === 'tree') {
    container.innerHTML = `<div class="tree-root">${renderTreeNode(activeFileData.tree)}</div>`;
  } else if (activeTab === 'raw') {
    container.innerHTML = `<pre class="xml-code"><code>${escapeHtml(activeFileData.raw)}</code></pre>`;
  }
}

// 5. Specialized Dashboard Renderers
function renderDashboardView(data) {
  const type = data.file_type;
  if (type === 'implementation_plan') {
    return renderImplementationPlan(data.specialized);
  } else if (type === 'mcp_documentation') {
    return renderMcpDocumentation(data.specialized);
  } else if (type === 'comparative_analysis') {
    return renderComparativeAnalysis(data.specialized);
  } else if (type === 'strategy_overhaul') {
    return renderStrategyOverhaul(data.specialized);
  } else {
    return renderGenericSummary(data);
  }
}

function renderImplementationPlan(spec) {
  if (!spec) return '<div>No plan data available.</div>';

  const sum = spec.summary || {};
  const prog = spec.progress || { total_tasks: 0, completed_tasks: 0, percent: 0 };

  let html = `
    <div class="dashboard-grid">
      <!-- Top Metrics -->
      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-card-title">Plan Progress</div>
          <div class="stat-card-value">${prog.percent}%</div>
          <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.25rem;">
            ${prog.completed_tasks} of ${prog.total_tasks} Tasks Completed
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-card-title">Phases</div>
          <div class="stat-card-value">${spec.phases.length}</div>
          <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.25rem;">P1 to P6 Lifecycles</div>
        </div>
        <div class="stat-card">
          <div class="stat-card-title">Decision Gates</div>
          <div class="stat-card-value">${spec.gates.length}</div>
          <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.25rem;">G0 to G6 Gates</div>
        </div>
        <div class="stat-card">
          <div class="stat-card-title">Active Campaigns</div>
          <div class="stat-card-value">${spec.campaigns.length}</div>
          <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.25rem;">Discovery Tracks</div>
        </div>
      </div>

      <!-- Positioning Card -->
      <div class="section-card">
        <div class="section-header">
          <h3>Core Positioning & Rate Ladder</h3>
          <span class="badge badge-verified">Approved Strategy</span>
        </div>
        <div class="section-body">
          <p style="font-size: 1.05rem; font-weight: 600; color: var(--text-main); margin-bottom: 0.75rem;">
            "${escapeHtml(sum.positioning || '')}"
          </p>
          <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem;">
            ${(sum.rate_ladder || []).map(r => `
              <span class="badge badge-medium" style="padding: 0.3rem 0.6rem;">
                Step ${r.order}: $${r.rate}/hr (${r.gate})
              </span>
            `).join('')}
          </div>
          <p style="font-size: 0.85rem; color: var(--text-muted);">
            <strong>Offer Ladder:</strong> ${escapeHtml(sum.offer_ladder_summary || '')}
          </p>
        </div>
      </div>

      <!-- Phases & Tasks Section -->
      <div class="section-card">
        <div class="section-header">
          <h3>Phases & Actionable Tasks</h3>
          <span style="font-size: 0.85rem; color: var(--text-muted);">Filter by Phase</span>
        </div>
        <div class="section-body">
          ${spec.phases.map(p => `
            <div style="margin-bottom: 1.5rem;">
              <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.75rem;">
                <h4 style="font-size: 0.95rem; font-weight: 700; color: var(--accent-color);">
                  ${p.id}: ${escapeHtml(p.name)}
                </h4>
                <span style="font-size: 0.8rem; color: var(--text-muted);">${escapeHtml(p.window || '')}</span>
              </div>
              <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 0.75rem;">${escapeHtml(p.goal || '')}</p>

              <div class="task-grid">
                ${p.tasks.map(t => `
                  <div class="task-card status-${t.status}">
                    <div class="task-header">
                      <span class="badge badge-${t.status}">${t.status}</span>
                      <span class="badge badge-${t.priority}">${t.priority}</span>
                      <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 600;">Day ${t.day}</span>
                    </div>
                    <div class="task-title">${t.id} - ${escapeHtml(t.title)}</div>
                    <div class="task-desc">${escapeHtml(t.description)}</div>
                    <div class="task-footer">
                      <span>Owner: <strong>${t.owner}</strong></span>
                      <span>${escapeHtml(t.tool || 'N/A')}</span>
                    </div>
                  </div>
                `).join('')}
              </div>
            </div>
          `).join('')}
        </div>
      </div>

      <!-- Decision Gates Table -->
      <div class="section-card">
        <div class="section-header">
          <h3>Decision Gates</h3>
        </div>
        <div class="section-body" style="padding: 0;">
          <table class="data-table">
            <thead>
              <tr>
                <th>Gate</th>
                <th>When</th>
                <th>Question</th>
                <th>Success Criteria</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              ${spec.gates.map(g => `
                <tr>
                  <td><strong>${g.id}</strong></td>
                  <td>${g.when}</td>
                  <td>${escapeHtml(g.question)}</td>
                  <td>${escapeHtml(g.metrics)}</td>
                  <td><span class="badge badge-${g.status}">${g.status}</span></td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>

      <!-- Live Verification Registry -->
      <div class="section-card">
        <div class="section-header">
          <h3>Verify Live Registry</h3>
        </div>
        <div class="section-body" style="padding: 0;">
          <table class="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Description</th>
                <th>Used In</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              ${spec.verify_live.map(vl => `
                <tr>
                  <td><strong>${vl.id}</strong></td>
                  <td>${escapeHtml(vl.text)}</td>
                  <td><code>${escapeHtml(vl.used_in)}</code></td>
                  <td>
                    <span class="badge ${vl.verified ? 'badge-verified' : 'badge-unverified'}">
                      ${vl.status}
                    </span>
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  return html;
}

function renderMcpDocumentation(spec) {
  if (!spec) return '<div>No MCP tools data available.</div>';

  return `
    <div class="dashboard-grid">
      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-card-title">Available Tools</div>
          <div class="stat-card-value">${spec.tool_count}</div>
          <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.25rem;">Across ${spec.domain_count} Domains</div>
        </div>
        <div class="stat-card">
          <div class="stat-card-title">Error Codes</div>
          <div class="stat-card-value">${spec.errors.length}</div>
          <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.25rem;">Standard Troubleshooting Codes</div>
        </div>
      </div>

      ${spec.domains.map(d => `
        <div class="section-card">
          <div class="section-header">
            <h3>Domain: ${escapeHtml(d.name)}</h3>
            <span class="badge badge-medium">${d.tools.length} Tools</span>
          </div>
          <div class="section-body" style="padding: 0;">
            <table class="data-table">
              <thead>
                <tr>
                  <th style="width: 25%;">Tool Name</th>
                  <th style="width: 35%;">Description</th>
                  <th>Parameters</th>
                </tr>
              </thead>
              <tbody>
                ${d.tools.map(t => `
                  <tr>
                    <td><strong>${escapeHtml(t.id)}</strong></td>
                    <td style="color: var(--text-muted);">${escapeHtml(t.description || '')}</td>
                    <td>
                      ${(t.parameters || []).map(p => `
                        <div style="margin-bottom: 0.25rem;">
                          <code>${p.name}</code> <span style="font-size: 0.75rem; color: var(--text-muted);">(${p.type}${p.required ? ', req' : ''})</span>
                        </div>
                      `).join('')}
                    </td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

function renderComparativeAnalysis(spec) {
  if (!spec) return '<div>No comparative data available.</div>';

  return `
    <div class="dashboard-grid">
      <div class="section-card">
        <div class="section-header">
          <h3>Consensus Verdict</h3>
        </div>
        <div class="section-body">
          <p style="font-size: 1rem; line-height: 1.6;">${escapeHtml(spec.verdict || 'No explicit verdict recorded.')}</p>
        </div>
      </div>

      <div class="section-card">
        <div class="section-header">
          <h3>Reviewer Document Evaluations</h3>
        </div>
        <div class="section-body" style="padding: 0;">
          <table class="data-table">
            <thead>
              <tr>
                <th>Document</th>
                <th>Verdict</th>
                <th>Score</th>
                <th>Key Findings</th>
              </tr>
            </thead>
            <tbody>
              ${spec.document_scores.map(doc => `
                <tr>
                  <td><strong>${escapeHtml(doc.name)}</strong></td>
                  <td><span class="badge badge-verified">${escapeHtml(doc.verdict || 'N/A')}</span></td>
                  <td>${escapeHtml(doc.score || 'N/A')}</td>
                  <td>${escapeHtml(doc.notes || '')}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>

      <div class="section-card">
        <div class="section-header">
          <h3>Consensus Agreements (${spec.agreements.length})</h3>
        </div>
        <div class="section-body">
          <ul style="padding-left: 1.25rem;">
            ${spec.agreements.map(a => `<li style="margin-bottom: 0.5rem;">${escapeHtml(a)}</li>`).join('')}
          </ul>
        </div>
      </div>
    </div>
  `;
}

function renderStrategyOverhaul(spec) {
  return `
    <div class="dashboard-grid">
      <div class="section-card">
        <div class="section-header">
          <h3>Strategy Positioning</h3>
        </div>
        <div class="section-body">
          <p style="font-size: 1.1rem; font-weight: 600; color: var(--accent-color);">
            ${escapeHtml(spec.positioning || 'Standard Strategy Overview')}
          </p>
          <p style="margin-top: 0.5rem; color: var(--text-muted);">${escapeHtml(spec.summary || '')}</p>
        </div>
      </div>
    </div>
  `;
}

function renderGenericSummary(data) {
  return `
    <div class="section-card">
      <div class="section-header">
        <h3>Generic XML Overview: &lt;${data.root_tag}&gt;</h3>
      </div>
      <div class="section-body">
        <p style="color: var(--text-muted); margin-bottom: 1rem;">
          This XML document is parsed and ready to explore in the <strong>Structured Tree</strong> and <strong>Raw XML</strong> tabs.
        </p>
        <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
          ${Object.entries(data.attributes || {}).map(([k, v]) => `
            <span class="tree-attr">${k}="${v}"</span>
          `).join('')}
        </div>
      </div>
    </div>
  `;
}

// 6. Tree View Renderer
function renderTreeNode(node) {
  if (!node) return '';

  const attrs = Object.entries(node.attrib || {})
    .map(([k, v]) => `<span class="tree-attr">${k}="${escapeHtml(v)}"</span>`)
    .join(' ');

  let contentHtml = '';
  if (node.text) {
    contentHtml += `<span class="tree-text">${escapeHtml(node.text)}</span>`;
  }

  if (node.children && node.children.length > 0) {
    contentHtml += `
      <div class="tree-children">
        ${node.children.map(child => renderTreeNode(child)).join('')}
      </div>
    `;
  }

  return `
    <div class="tree-node">
      <div class="tree-header">
        <span class="tree-tag">&lt;${node.tag}&gt;</span>
        ${attrs}
        ${node.text ? `<span style="color: var(--text-muted); font-size: 0.8rem;">: ${escapeHtml(node.text.slice(0, 80))}</span>` : ''}
      </div>
      ${contentHtml}
    </div>
  `;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
