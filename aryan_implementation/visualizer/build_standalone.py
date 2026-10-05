"""
Standalone HTML Visualizer Builder
Compiles all workspace XML files into a zero-dependency, single-file HTML application (visualizer.html)
with native client-side XML parsing and File System Access API live disk watching.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Any


def get_category(relpath: str) -> str:
    norm = relpath.replace("\\", "/").lower()
    if "implementation_plan" in norm:
        return "Implementation Plans"
    elif "mcp_documentation" in norm:
        return "MCP Protocols & Schemas"
    elif "comparitive_analysis" in norm or "comparative_analysis" in norm:
        return "Comparative Analyses"
    elif "overhaul" in norm or "strategy" in norm:
        return "Strategy Overhaul Plans"
    return "Other XML Documents"


def build_standalone_html(workspace_root: Path, output_file: Path) -> Path:
    xml_files: List[Dict[str, Any]] = []

    # Find all XML files, excluding hidden or git directories
    for path in sorted(workspace_root.glob("**/*.xml")):
        if ".git" in path.parts or ".pytest_cache" in path.parts:
            continue
        relpath = path.relative_to(workspace_root).as_posix()
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            xml_files.append({
                "name": path.name,
                "relpath": relpath,
                "category": get_category(relpath),
                "size_bytes": len(content.encode("utf-8")),
                "content": content,
            })
        except Exception as e:
            print(f"Warning: Failed to read {path}: {e}")

    embedded_json = json.dumps(xml_files)

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Upwork MCP XML Visualizer (Serverless Edition)</title>
  <style>
    :root {{
      --bg-primary: #0b0f19;
      --bg-secondary: #111827;
      --bg-card: #1f2937;
      --bg-card-hover: #374151;
      --border-color: #374151;
      --text-main: #f9fafb;
      --text-muted: #9ca3af;
      --accent-color: #38bdf8;
      --accent-hover: #0284c7;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --info: #6366f1;
      --purple: #a855f7;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background-color: var(--bg-primary);
      color: var(--text-main);
      line-height: 1.5;
      display: flex;
      height: 100vh;
      overflow: hidden;
    }}

    /* Sidebar */
    #sidebar {{
      width: 320px;
      background-color: var(--bg-secondary);
      border-right: 1px solid var(--border-color);
      display: flex;
      flex-direction: column;
      flex-shrink: 0;
    }}

    .sidebar-header {{
      padding: 1.25rem;
      border-bottom: 1px solid var(--border-color);
    }}

    .sidebar-header h1 {{
      font-size: 1.1rem;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      color: var(--accent-color);
    }}

    .mode-badge {{
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.75rem;
      padding: 0.25rem 0.6rem;
      border-radius: 9999px;
      background: rgba(16, 185, 129, 0.15);
      color: var(--success);
      margin-top: 0.6rem;
      font-weight: 600;
    }}

    .pulse-dot {{
      width: 8px;
      height: 8px;
      background-color: var(--success);
      border-radius: 50%;
      display: inline-block;
      animation: pulse 2s infinite;
    }}

    @keyframes pulse {{
      0% {{ transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }}
      70% {{ transform: scale(1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }}
      100% {{ transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }}
    }}

    .sidebar-actions {{
      padding: 0.75rem 1.25rem;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      border-bottom: 1px solid var(--border-color);
      background: rgba(0, 0, 0, 0.2);
    }}

    .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      padding: 0.5rem 0.75rem;
      font-size: 0.8rem;
      font-weight: 600;
      border-radius: 6px;
      border: 1px solid var(--border-color);
      background: var(--bg-card);
      color: var(--text-main);
      cursor: pointer;
      transition: all 0.15s ease;
      text-decoration: none;
    }}

    .btn:hover {{
      background: var(--bg-card-hover);
      border-color: var(--accent-color);
    }}

    .btn-primary {{
      background: #0369a1;
      border-color: #0284c7;
      color: #fff;
    }}

    .btn-primary:hover {{
      background: #0284c7;
    }}

    .file-search {{
      padding: 0.75rem 1.25rem;
      border-bottom: 1px solid var(--border-color);
    }}

    .file-search input {{
      width: 100%;
      padding: 0.5rem 0.75rem;
      background-color: var(--bg-primary);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      color: var(--text-main);
      font-size: 0.85rem;
    }}

    .file-search input:focus {{
      outline: none;
      border-color: var(--accent-color);
    }}

    .file-list {{
      flex: 1;
      overflow-y: auto;
      padding: 0.5rem;
    }}

    .file-category {{
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      padding: 0.75rem 0.75rem 0.25rem;
      font-weight: 700;
    }}

    .file-item {{
      display: flex;
      flex-direction: column;
      padding: 0.6rem 0.75rem;
      border-radius: 6px;
      cursor: pointer;
      margin-bottom: 2px;
      transition: background-color 0.15s;
    }}

    .file-item:hover {{
      background-color: var(--bg-card-hover);
    }}

    .file-item.active {{
      background-color: #1e3a8a;
      border-left: 3px solid var(--accent-color);
    }}

    .file-name {{
      font-size: 0.85rem;
      font-weight: 500;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}

    .file-meta {{
      font-size: 0.7rem;
      color: var(--text-muted);
      margin-top: 2px;
      display: flex;
      justify-content: space-between;
    }}

    /* Main Content Area */
    #main-content {{
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      background-color: var(--bg-primary);
    }}

    .top-header {{
      padding: 1rem 1.75rem;
      background-color: var(--bg-secondary);
      border-bottom: 1px solid var(--border-color);
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-shrink: 0;
    }}

    .file-info h2 {{
      font-size: 1.25rem;
      font-weight: 700;
      color: var(--text-main);
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }}

    .file-path {{
      font-size: 0.8rem;
      color: var(--text-muted);
      font-family: monospace;
      margin-top: 2px;
    }}

    .tab-bar {{
      display: flex;
      gap: 0.5rem;
    }}

    .tab-btn {{
      padding: 0.45rem 0.9rem;
      font-size: 0.85rem;
      font-weight: 600;
      background: transparent;
      border: 1px solid transparent;
      color: var(--text-muted);
      border-radius: 6px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 0.4rem;
      transition: all 0.15s;
    }}

    .tab-btn:hover {{
      color: var(--text-main);
      background-color: var(--bg-card);
    }}

    .tab-btn.active {{
      color: var(--accent-color);
      background-color: var(--bg-card);
      border-color: var(--border-color);
    }}

    .view-container {{
      flex: 1;
      overflow-y: auto;
      padding: 1.75rem;
    }}

    /* Cards & Grids */
    .dashboard-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 1.25rem;
      margin-bottom: 1.5rem;
    }}

    .stat-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 1.25rem;
      display: flex;
      flex-direction: column;
    }}

    .stat-label {{
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      font-weight: 600;
      margin-bottom: 0.5rem;
    }}

    .stat-val {{
      font-size: 1.75rem;
      font-weight: 800;
      color: var(--text-main);
    }}

    .stat-val.accent {{ color: var(--accent-color); }}
    .stat-val.success {{ color: var(--success); }}
    .stat-val.warning {{ color: var(--warning); }}

    .stat-sub {{
      font-size: 0.75rem;
      color: var(--text-muted);
      margin-top: 0.25rem;
    }}

    .section-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 1.5rem;
      margin-bottom: 1.5rem;
    }}

    .section-title {{
      font-size: 1.1rem;
      font-weight: 700;
      margin-bottom: 1rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 0.5rem;
    }}

    /* Badges */
    .badge {{
      display: inline-block;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      font-size: 0.7rem;
      font-weight: 700;
      text-transform: uppercase;
    }}

    .badge-done {{ background: rgba(16, 185, 129, 0.2); color: var(--success); border: 1px solid rgba(16, 185, 129, 0.4); }}
    .badge-todo {{ background: rgba(245, 158, 11, 0.2); color: var(--warning); border: 1px solid rgba(245, 158, 11, 0.4); }}
    .badge-critical {{ background: rgba(239, 68, 68, 0.2); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.4); }}
    .badge-high {{ background: rgba(245, 158, 11, 0.2); color: var(--warning); border: 1px solid rgba(245, 158, 11, 0.4); }}
    .badge-medium {{ background: rgba(56, 189, 248, 0.2); color: var(--accent-color); border: 1px solid rgba(56, 189, 248, 0.4); }}
    .badge-low {{ background: rgba(156, 163, 175, 0.2); color: var(--text-muted); border: 1px solid rgba(156, 163, 175, 0.4); }}
    .badge-tag {{ background: rgba(99, 102, 241, 0.2); color: var(--info); border: 1px solid rgba(99, 102, 241, 0.4); }}

    /* Task Board */
    .task-filters {{
      display: flex;
      gap: 0.5rem;
      margin-bottom: 1rem;
      flex-wrap: wrap;
    }}

    .filter-btn {{
      padding: 0.35rem 0.75rem;
      font-size: 0.75rem;
      background: var(--bg-secondary);
      border: 1px solid var(--border-color);
      border-radius: 4px;
      color: var(--text-muted);
      cursor: pointer;
    }}

    .filter-btn.active {{
      background: var(--accent-color);
      color: #0b0f19;
      font-weight: 700;
    }}

    .task-card {{
      background: var(--bg-secondary);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 1rem;
      margin-bottom: 0.75rem;
      transition: all 0.15s;
    }}

    .task-card.is-done {{
      border-left: 4px solid var(--success);
    }}

    .task-card.is-todo {{
      border-left: 4px solid var(--warning);
    }}

    .task-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 0.4rem;
    }}

    .task-title {{
      font-weight: 600;
      font-size: 0.95rem;
      color: var(--text-main);
    }}

    .task-meta {{
      display: flex;
      gap: 0.4rem;
    }}

    .task-desc {{
      font-size: 0.85rem;
      color: var(--text-muted);
      margin-bottom: 0.5rem;
    }}

    .task-details {{
      display: flex;
      gap: 1.5rem;
      font-size: 0.75rem;
      color: var(--text-muted);
      border-top: 1px dashed var(--border-color);
      padding-top: 0.5rem;
      margin-top: 0.5rem;
    }}

    .task-details span strong {{
      color: var(--text-main);
    }}

    /* Tables */
    .data-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
    }}

    .data-table th, .data-table td {{
      padding: 0.6rem 0.75rem;
      text-align: left;
      border-bottom: 1px solid var(--border-color);
    }}

    .data-table th {{
      background: var(--bg-secondary);
      color: var(--text-muted);
      font-weight: 600;
      text-transform: uppercase;
      font-size: 0.7rem;
      letter-spacing: 0.05em;
    }}

    .data-table tr:hover td {{
      background: rgba(255, 255, 255, 0.02);
    }}

    /* Collapsible Tree Explorer */
    .tree-node {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.85rem;
      line-height: 1.6;
      margin-left: 1.25rem;
      border-left: 1px dotted var(--border-color);
      padding-left: 0.5rem;
    }}

    .tree-node-header {{
      display: flex;
      align-items: baseline;
      gap: 0.4rem;
      cursor: pointer;
      user-select: none;
      padding: 2px 4px;
      border-radius: 4px;
    }}

    .tree-node-header:hover {{
      background: var(--bg-card-hover);
    }}

    .tree-toggle {{
      font-size: 0.7rem;
      color: var(--text-muted);
      width: 12px;
      display: inline-block;
    }}

    .tree-tag {{
      color: #f43f5e;
      font-weight: 600;
    }}

    .tree-attr {{
      color: #38bdf8;
      font-size: 0.8rem;
    }}

    .tree-val {{
      color: #e2e8f0;
    }}

    .tree-text {{
      color: #34d399;
      margin-left: 0.5rem;
      word-break: break-word;
    }}

    /* Raw Code Viewer */
    .raw-xml-code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.82rem;
      background: var(--bg-secondary);
      padding: 1.5rem;
      border-radius: 8px;
      border: 1px solid var(--border-color);
      overflow-x: auto;
      white-space: pre-wrap;
      word-break: break-all;
      color: #e2e8f0;
      line-height: 1.6;
    }}

    /* Drop Zone */
    #dropzone-overlay {{
      display: none;
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(11, 15, 25, 0.85);
      border: 3px dashed var(--accent-color);
      z-index: 9999;
      justify-content: center;
      align-items: center;
      font-size: 1.5rem;
      font-weight: 700;
      color: var(--accent-color);
    }}

    /* Scrollbars */
    ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
    ::-webkit-scrollbar-track {{ background: var(--bg-primary); }}
    ::-webkit-scrollbar-thumb {{ background: var(--border-color); border-radius: 3px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: var(--text-muted); }}
  </style>
</head>
<body>

  <!-- Fullscreen Dropzone Overlay -->
  <div id="dropzone-overlay">Drop any XML file to inspect instantly</div>

  <!-- Sidebar -->
  <div id="sidebar">
    <div class="sidebar-header">
      <h1>⚡ Upwork MCP Visualizer</h1>
      <div id="mode-badge" class="mode-badge">
        <span class="pulse-dot"></span>
        <span id="mode-text">Snapshot Mode (Zero Server)</span>
      </div>
    </div>

    <div class="sidebar-actions">
      <button id="btn-connect-folder" class="btn btn-primary" title="Connect local folder using File System Access API for 0-server live disk sync">
        🟢 Enable Live Disk Watch
      </button>
      <label class="btn" style="cursor: pointer;">
        📂 Open External XML
        <input type="file" id="file-input" accept=".xml" style="display: none;">
      </label>
    </div>

    <div class="file-search">
      <input type="text" id="search-input" placeholder="Search XML files...">
    </div>

    <div id="file-list" class="file-list"></div>
  </div>

  <!-- Main Content Area -->
  <div id="main-content">
    <div class="top-header">
      <div class="file-info">
        <h2 id="active-filename">Select a file</h2>
        <div id="active-filepath" class="file-path"></div>
      </div>
      <div class="tab-bar">
        <button class="tab-btn active" data-tab="dashboard">📊 Dashboard</button>
        <button class="tab-btn" data-tab="tree">🌳 Interactive Tree</button>
        <button class="tab-btn" data-tab="raw">📝 Raw XML</button>
      </div>
    </div>

    <div id="view-container" class="view-container"></div>
  </div>

  <!-- Embedded Dataset -->
  <script id="embedded-xml-data" type="application/json">
    {embedded_json}
  </script>

  <script>
    /**
     * Serverless Dynamic XML Visualizer Engine
     * Pure client-side parsing, zero-server disk watching via File System Access API.
     */
    let filesRegistry = [];
    let activeFile = null;
    let activeTab = 'dashboard';
    let dirHandle = null;
    let diskWatchInterval = null;
    let watchedFileHandles = new Map(); // relpath -> FileSystemFileHandle
    let fileTimestamps = new Map(); // relpath -> lastModified

    // 1. Initialization
    document.addEventListener('DOMContentLoaded', () => {{
      loadEmbeddedData();
      setupEventListeners();
      setupDragAndDrop();
    }});

    function loadEmbeddedData() {{
      try {{
        const rawJson = document.getElementById('embedded-xml-data').textContent;
        filesRegistry = JSON.parse(rawJson);
        renderFileList(filesRegistry);

        if (filesRegistry.length > 0) {{
          const preferred = filesRegistry.find(f => f.name.includes('ARYAN_IMPLEMENTATION_PLAN')) || filesRegistry[0];
          selectFile(preferred.relpath);
        }}
      }} catch (err) {{
        console.error('Failed to parse embedded XML data:', err);
      }}
    }}

    function setupEventListeners() {{
      // Tabs
      document.querySelectorAll('.tab-btn').forEach(btn => {{
        btn.addEventListener('click', () => {{
          document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          activeTab = btn.getAttribute('data-tab');
          renderActiveView();
        }});
      }});

      // Search input
      document.getElementById('search-input').addEventListener('input', (e) => {{
        renderFileList(filesRegistry);
      }});

      // File input picker
      document.getElementById('file-input').addEventListener('change', async (e) => {{
        const file = e.target.files[0];
        if (file) {{
          const text = await file.text();
          importFile(file.name, text);
        }}
      }});

      // Live disk watch button
      document.getElementById('btn-connect-folder').addEventListener('click', initFileSystemAccess);
    }}

    // 2. File System Access API (Zero-server real-time disk watch)
    async function initFileSystemAccess() {{
      if (!('showDirectoryPicker' in window)) {{
        alert('File System Access API is not supported in this browser. Please use Chrome, Edge, Brave, or Opera for live disk watching.');
        return;
      }}

      try {{
        dirHandle = await window.showDirectoryPicker({{ mode: 'read' }});
        const badge = document.getElementById('mode-badge');
        const text = document.getElementById('mode-text');
        text.textContent = 'Live Disk Sync Active (1s polling)';
        badge.style.background = 'rgba(16, 185, 129, 0.2)';
        badge.style.color = 'var(--success)';

        document.getElementById('btn-connect-folder').innerHTML = '🔄 Re-scan Workspace Folder';

        // Initial scan
        await scanWorkspaceDirectory(dirHandle);

        // Start polling interval every 1 second
        if (diskWatchInterval) clearInterval(diskWatchInterval);
        diskWatchInterval = setInterval(pollFileChanges, 1000);

        console.log('[Live Disk Watch] Connected to folder:', dirHandle.name);
      }} catch (err) {{
        if (err.name !== 'AbortError') {{
          console.error('Error connecting folder:', err);
          alert('Could not access folder: ' + err.message);
        }}
      }}
    }}

    async function scanWorkspaceDirectory(dir, currentPath = '') {{
      for await (const [name, handle] of dir.entries()) {{
        if (name.startsWith('.') || name === 'node_modules' || name === '__pycache__') continue;
        const rel = currentPath ? `${{currentPath}}/${{name}}` : name;
        if (handle.kind === 'file' && name.toLowerCase().endsWith('.xml')) {{
          watchedFileHandles.set(rel, handle);
          const file = await handle.getFile();
          fileTimestamps.set(rel, file.lastModified);

          // Update or add to filesRegistry
          const existing = filesRegistry.find(f => f.relpath === rel || f.relpath.replace(/\\\\/g, '/') === rel);
          const text = await file.text();
          if (existing) {{
            existing.content = text;
            existing.size_bytes = file.size;
          }} else {{
            filesRegistry.push({{
              name: name,
              relpath: rel,
              category: getCategory(rel),
              size_bytes: file.size,
              content: text
            }});
          }}
        }} else if (handle.kind === 'directory') {{
          await scanWorkspaceDirectory(handle, rel);
        }}
      }}
      renderFileList(filesRegistry);
    }}

    async function pollFileChanges() {{
      for (const [rel, handle] of watchedFileHandles.entries()) {{
        try {{
          const file = await handle.getFile();
          const prevTime = fileTimestamps.get(rel);
          if (prevTime && file.lastModified > prevTime) {{
            fileTimestamps.set(rel, file.lastModified);
            const text = await file.text();
            console.log('[Live Disk Watch] Detected update in:', rel);

            const item = filesRegistry.find(f => f.relpath === rel || f.relpath.replace(/\\\\/g, '/') === rel);
            if (item) {{
              item.content = text;
              item.size_bytes = file.size;
            }}

            if (activeFile && (activeFile.relpath === rel || activeFile.relpath.replace(/\\\\/g, '/') === rel)) {{
              activeFile.content = text;
              activeFile.size_bytes = file.size;
              flashIndicator();
              renderActiveView();
            }}
          }}
        }} catch (e) {{
          // ignore transient locks
        }}
      }}
    }}

    function flashIndicator() {{
      const badge = document.getElementById('mode-badge');
      badge.style.background = 'rgba(56, 189, 248, 0.4)';
      setTimeout(() => {{
        badge.style.background = 'rgba(16, 185, 129, 0.2)';
      }}, 800);
    }}

    function getCategory(path) {{
      const norm = path.toLowerCase();
      if (norm.includes('implementation_plan')) return 'Implementation Plans';
      if (norm.includes('mcp_documentation')) return 'MCP Protocols & Schemas';
      if (norm.includes('comparitive_analysis') || norm.includes('comparative_analysis')) return 'Comparative Analyses';
      if (norm.includes('overhaul') || norm.includes('strategy')) return 'Strategy Overhaul Plans';
      return 'Other XML Documents';
    }}

    // 3. Drag and Drop Handling
    function setupDragAndDrop() {{
      const overlay = document.getElementById('dropzone-overlay');
      window.addEventListener('dragenter', (e) => {{
        e.preventDefault();
        overlay.style.display = 'flex';
      }});
      overlay.addEventListener('dragover', (e) => {{
        e.preventDefault();
      }});
      overlay.addEventListener('dragleave', (e) => {{
        e.preventDefault();
        overlay.style.display = 'none';
      }});
      overlay.addEventListener('drop', async (e) => {{
        e.preventDefault();
        overlay.style.display = 'none';
        for (const file of e.dataTransfer.files) {{
          if (file.name.toLowerCase().endsWith('.xml')) {{
            const text = await file.text();
            importFile(file.name, text);
            break;
          }}
        }}
      }});
    }}

    function importFile(name, content) {{
      const existing = filesRegistry.find(f => f.name === name);
      if (existing) {{
        existing.content = content;
        existing.size_bytes = content.length;
        selectFile(existing.relpath);
      }} else {{
        const newFile = {{
          name: name,
          relpath: 'imported/' + name,
          category: 'Imported Files',
          size_bytes: content.length,
          content: content
        }};
        filesRegistry.unshift(newFile);
        renderFileList(filesRegistry);
        selectFile(newFile.relpath);
      }}
    }}

    // 4. File List Rendering
    function renderFileList(files) {{
      const container = document.getElementById('file-list');
      const search = document.getElementById('search-input').value.toLowerCase();
      const filtered = files.filter(f => f.name.toLowerCase().includes(search) || f.category.toLowerCase().includes(search));

      const groups = {{}};
      filtered.forEach(f => {{
        groups[f.category] = groups[f.category] || [];
        groups[f.category].push(f);
      }});

      let html = '';
      for (const [cat, catFiles] of Object.entries(groups)) {{
        html += `<div class="file-category">${{cat}} (${{catFiles.length}})</div>`;
        catFiles.forEach(f => {{
          const isActive = activeFile && (activeFile.relpath === f.relpath) ? 'active' : '';
          const sizeKb = (f.size_bytes / 1024).toFixed(1);
          html += `
            <div class="file-item ${{isActive}}" onclick="selectFile('${{f.relpath}}')">
              <div class="file-name">${{escapeHtml(f.name)}}</div>
              <div class="file-meta">
                <span>${{sizeKb}} KB</span>
              </div>
            </div>
          `;
        }});
      }}
      container.innerHTML = html;
    }}

    function selectFile(relpath) {{
      activeFile = filesRegistry.find(f => f.relpath === relpath);
      if (!activeFile) return;

      document.getElementById('active-filename').textContent = activeFile.name;
      document.getElementById('active-filepath').textContent = activeFile.relpath;

      renderFileList(filesRegistry);
      renderActiveView();
    }}

    // 5. XML Parsing & View Rendering
    function renderActiveView() {{
      if (!activeFile) return;
      const container = document.getElementById('view-container');
      const parser = new DOMParser();
      const xmlDoc = parser.parseFromString(activeFile.content, 'text/xml');

      // Check parse error
      const parseError = xmlDoc.querySelector('parsererror');
      if (parseError) {{
        container.innerHTML = `
          <div class="section-card" style="border-left: 4px solid var(--danger);">
            <div class="section-title" style="color: var(--danger);">⚠️ XML Parse Error</div>
            <pre class="raw-xml-code" style="color: #fca5a5;">${{escapeHtml(parseError.textContent)}}</pre>
          </div>
        `;
        return;
      }}

      if (activeTab === 'raw') {{
        container.innerHTML = `<pre class="raw-xml-code">${{escapeHtml(activeFile.content)}}</pre>`;
      }} else if (activeTab === 'tree') {{
        container.innerHTML = `
          <div class="section-card">
            <div class="section-title">
              <span>Interactive XML DOM Tree</span>
              <span class="badge badge-tag">${{xmlDoc.documentElement.tagName}}</span>
            </div>
            ${{renderTreeNode(xmlDoc.documentElement)}}
          </div>
        `;
        setupTreeToggles();
      }} else {{
        // Dashboard
        const type = detectDocType(xmlDoc, activeFile.name);
        if (type === 'plan') {{
          container.innerHTML = renderPlanDashboard(xmlDoc);
          setupTaskFilters();
        }} else if (type === 'mcp') {{
          container.innerHTML = renderMcpDashboard(xmlDoc);
        }} else if (type === 'comparison') {{
          container.innerHTML = renderComparisonDashboard(xmlDoc);
        }} else {{
          container.innerHTML = renderGenericDashboard(xmlDoc);
        }}
      }}
    }}

    function detectDocType(doc, filename) {{
      const rootTag = doc.documentElement.tagName.toLowerCase();
      const name = filename.toLowerCase();
      if (rootTag === 'implementation_plan' || name.includes('implementation_plan')) return 'plan';
      if (name.includes('mcp_documentation') || rootTag.includes('mcp')) return 'mcp';
      if (name.includes('comparitive_analysis') || name.includes('comparative_analysis') || name.includes('consensus')) return 'comparison';
      return 'generic';
    }}

    // 6. Specialized Dashboards
    function renderPlanDashboard(doc) {{
      const tasks = Array.from(doc.querySelectorAll('tasks task, task'));
      const totalTasks = tasks.length;
      const completedTasks = tasks.filter(t => t.getAttribute('status') === 'done').length;
      const percent = totalTasks ? Math.round((completedTasks / totalTasks) * 100) : 0;

      const vlItems = Array.from(doc.querySelectorAll('verify_live_registry item'));
      const vlDone = vlItems.filter(v => v.getAttribute('verified') === 'true').length;

      const phItems = Array.from(doc.querySelectorAll('placeholders_registry placeholder'));
      const phDone = phItems.filter(p => p.getAttribute('status') === 'done').length;

      // Summary
      const pos = doc.querySelector('summary positioning')?.textContent || 'AI Systems Architect & Upwork MCP Acquisition Engine';
      const stickerRate = doc.querySelector('summary title')?.getAttribute('rate') || '$65/hr';
      const offerLadderSum = doc.querySelector('summary offer_ladder_summary')?.textContent || '';

      // Phases
      const phases = Array.from(doc.querySelectorAll('phases phase, phase'));

      let phasesHtml = '';
      phases.forEach(p => {{
        const pid = p.getAttribute('id') || '';
        const pname = p.getAttribute('name') || p.querySelector('title')?.textContent || '';
        const ptasks = Array.from(p.querySelectorAll('tasks task, task'));
        const pDone = ptasks.filter(t => t.getAttribute('status') === 'done').length;

        phasesHtml += `
          <div class="section-card">
            <div class="section-title">
              <span>Phase ${{pid}}: ${{escapeHtml(pname)}}</span>
              <span class="badge badge-${{pDone === ptasks.length && ptasks.length > 0 ? 'done' : 'medium'}}">${{pDone}} / ${{ptasks.length}} Done</span>
            </div>
            <div class="task-list">
              ${{ptasks.map(t => renderTaskCard(t)).join('')}}
            </div>
          </div>
        `;
      }});

      // Decision Gates
      const gates = Array.from(doc.querySelectorAll('decision_gates gate'));
      let gatesHtml = '';
      if (gates.length > 0) {{
        gatesHtml = `
          <div class="section-card">
            <div class="section-title">Decision Gates</div>
            <table class="data-table">
              <thead>
                <tr>
                  <th>Gate</th>
                  <th>Day</th>
                  <th>Decision Criteria</th>
                  <th>Actions (Pass / Pivot)</th>
                </tr>
              </thead>
              <tbody>
                ${{gates.map(g => `
                  <tr>
                    <td><strong>${{g.getAttribute('id')}}: ${{escapeHtml(g.getAttribute('name') || '')}}</strong></td>
                    <td>Day ${{g.getAttribute('day') || '-'}}</td>
                    <td>${{escapeHtml(g.querySelector('criteria')?.textContent || g.getAttribute('criteria') || '-')}}</td>
                    <td>${{escapeHtml(g.querySelector('action')?.textContent || g.getAttribute('action') || '-')}}</td>
                  </tr>
                `).join('')}}
              </tbody>
            </table>
          </div>
        `;
      }}

      return `
        <div class="dashboard-grid">
          <div class="stat-card">
            <div class="stat-label">Overall Progress</div>
            <div class="stat-val accent">${{percent}}%</div>
            <div class="stat-sub">${{completedTasks}} of ${{totalTasks}} Tasks Completed</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Verified Live Registry</div>
            <div class="stat-val success">${{vlDone}} / ${{vlItems.length}}</div>
            <div class="stat-sub">Live Telemetry Items Confirmed</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Placeholders Resolved</div>
            <div class="stat-val warning">${{phDone}} / ${{phItems.length}}</div>
            <div class="stat-sub">Profile Facts & Permissions Set</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Target Rate & Ladder</div>
            <div class="stat-val">${{stickerRate}}</div>
            <div class="stat-sub">${{escapeHtml(offerLadderSum)}}</div>
          </div>
        </div>

        <div class="section-card" style="border-left: 4px solid var(--accent-color);">
          <div class="section-title">Master Positioning</div>
          <p style="font-size: 0.95rem; color: #e2e8f0;">${{escapeHtml(pos)}}</p>
        </div>

        <div class="task-filters">
          <span style="font-size: 0.8rem; color: var(--text-muted); align-self: center; margin-right: 0.5rem;">Filter Tasks:</span>
          <button class="filter-btn active" data-filter="all">All (${{totalTasks}})</button>
          <button class="filter-btn" data-filter="done">Completed (${{completedTasks}})</button>
          <button class="filter-btn" data-filter="todo">Remaining (${{totalTasks - completedTasks}})</button>
        </div>

        ${{phasesHtml}}
        ${{gatesHtml}}
      `;
    }}

    function renderTaskCard(t) {{
      const tid = t.getAttribute('id') || '';
      const status = t.getAttribute('status') || 'todo';
      const isDone = status === 'done';
      const priority = t.getAttribute('priority') || 'medium';
      const owner = t.getAttribute('owner') || 'agent';
      const day = t.getAttribute('day') || '-';
      const title = t.querySelector('title')?.textContent || t.getAttribute('title') || '';
      const desc = t.querySelector('description')?.textContent || '';
      const tool = t.querySelector('tool')?.textContent || '';
      const criteria = t.querySelector('acceptance_criteria')?.textContent || '';

      return `
        <div class="task-card ${{isDone ? 'is-done' : 'is-todo'}}" data-status="${{status}}">
          <div class="task-header">
            <div class="task-title">
              <span style="color: var(--accent-color); font-family: monospace; margin-right: 0.4rem;">${{tid}}</span>
              ${{escapeHtml(title)}}
            </div>
            <div class="task-meta">
              <span class="badge badge-${{isDone ? 'done' : 'todo'}}">${{status}}</span>
              <span class="badge badge-${{priority}}">${{priority}}</span>
              <span class="badge badge-tag">${{owner}}</span>
            </div>
          </div>
          ${{desc ? `<div class="task-desc">${{escapeHtml(desc)}}</div>` : ''}}
          <div class="task-details">
            ${{tool ? `<span><strong>Tool:</strong> ${{escapeHtml(tool)}}</span>` : ''}}
            <span><strong>Day:</strong> ${{day}}</span>
            ${{criteria ? `<span><strong>Criteria:</strong> ${{escapeHtml(criteria)}}</span>` : ''}}
          </div>
        </div>
      `;
    }}

    function renderMcpDashboard(doc) {{
      const tools = Array.from(doc.querySelectorAll('tool, tool_definition'));
      const domains = {{}};
      tools.forEach(t => {{
        const d = t.getAttribute('domain') || 'General';
        domains[d] = domains[d] || [];
        domains[d].push(t);
      }});

      let domainsHtml = '';
      for (const [dom, domTools] of Object.entries(domains)) {{
        domainsHtml += `
          <div class="section-card">
            <div class="section-title">
              <span>Domain: ${{dom}}</span>
              <span class="badge badge-tag">${{domTools.length}} Tools</span>
            </div>
            <table class="data-table">
              <thead>
                <tr>
                  <th style="width: 250px;">Tool Name</th>
                  <th>Action / Purpose</th>
                  <th style="width: 120px;">Mode</th>
                </tr>
              </thead>
              <tbody>
                ${{domTools.map(t => {{
                  const name = t.getAttribute('name') || t.querySelector('name')?.textContent || '';
                  const desc = t.querySelector('description')?.textContent || t.getAttribute('description') || '';
                  const readOnly = t.getAttribute('read_only') === 'true';
                  return `
                    <tr>
                      <td><code style="color: var(--accent-color); font-weight: 700;">${{name}}</code></td>
                      <td>${{escapeHtml(desc)}}</td>
                      <td><span class="badge badge-${{readOnly ? 'done' : 'critical'}}">${{readOnly ? 'Read Only' : 'Write / Confirm'}}</span></td>
                    </tr>
                  `;
                }}).join('')}}
              </tbody>
            </table>
          </div>
        `;
      }}

      return `
        <div class="dashboard-grid">
          <div class="stat-card">
            <div class="stat-label">Total Tools Registered</div>
            <div class="stat-val accent">${{tools.length}}</div>
            <div class="stat-sub">Official Upwork MCP Protocol</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Functional Domains</div>
            <div class="stat-val info">${{Object.keys(domains).length}}</div>
            <div class="stat-sub">Discovery, Bidding, Contracts, Messages</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Safety Non-Negotiables</div>
            <div class="stat-val success">100% Gated</div>
            <div class="stat-sub">Mandatory 2-Step Preview Confirmation</div>
          </div>
        </div>
        ${{domainsHtml}}
      `;
    }}

    function renderComparisonDashboard(doc) {{
      const agreements = Array.from(doc.querySelectorAll('agreement_points point, agreement'));
      const disagreements = Array.from(doc.querySelectorAll('disagreement_points point, disagreement'));

      return `
        <div class="dashboard-grid">
          <div class="stat-card">
            <div class="stat-label">Consensus Agreements</div>
            <div class="stat-val success">${{agreements.length}}</div>
            <div class="stat-sub">Adopted Across Strategic Evaluators</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Reviewer Splits / Disagreements</div>
            <div class="stat-val warning">${{disagreements.length}}</div>
            <div class="stat-sub">Reconciled in Aryan Implementation Plan</div>
          </div>
        </div>

        <div class="section-card">
          <div class="section-title">Key Consensus Decisions</div>
          <ul style="padding-left: 1.25rem; font-size: 0.9rem; line-height: 1.8;">
            ${{agreements.slice(0, 10).map(a => `<li>${{escapeHtml(a.textContent.trim())}}</li>`).join('')}}
          </ul>
        </div>

        ${{disagreements.length > 0 ? `
          <div class="section-card">
            <div class="section-title">Resolved Disagreements</div>
            <ul style="padding-left: 1.25rem; font-size: 0.9rem; line-height: 1.8;">
              ${{disagreements.slice(0, 10).map(d => `<li>${{escapeHtml(d.textContent.trim())}}</li>`).join('')}}
            </ul>
          </div>
        ` : ''}}
      `;
    }}

    function renderGenericDashboard(doc) {{
      const allElements = doc.querySelectorAll('*');
      const tagCounts = {{}};
      allElements.forEach(el => {{
        tagCounts[el.tagName] = (tagCounts[el.tagName] || 0) + 1;
      }});

      return `
        <div class="dashboard-grid">
          <div class="stat-card">
            <div class="stat-label">Total Elements</div>
            <div class="stat-val accent">${{allElements.length}}</div>
            <div class="stat-sub">Parsed XML Nodes</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Root Tag</div>
            <div class="stat-val info">&lt;${{doc.documentElement.tagName}}&gt;</div>
            <div class="stat-sub">${{doc.documentElement.attributes.length}} Attributes</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Unique Element Tags</div>
            <div class="stat-val warning">${{Object.keys(tagCounts).length}}</div>
            <div class="stat-sub">Distinct Tags in Document</div>
          </div>
        </div>

        <div class="section-card">
          <div class="section-title">Element Frequency</div>
          <table class="data-table">
            <thead>
              <tr><th>Tag Name</th><th>Occurrence Count</th></tr>
            </thead>
            <tbody>
              ${{Object.entries(tagCounts).slice(0, 15).map(([tag, count]) => `
                <tr>
                  <td><code style="color: var(--accent-color);">&lt;${{tag}}&gt;</code></td>
                  <td><strong>${{count}}</strong></td>
                </tr>
              `).join('')}}
            </tbody>
          </table>
        </div>
      `;
    }}

    // 7. Interactive Collapsible Tree
    function renderTreeNode(node) {{
      const hasChildren = node.children.length > 0;
      const text = Array.from(node.childNodes)
        .filter(n => n.nodeType === Node.TEXT_NODE)
        .map(n => n.textContent.trim())
        .join(' ');

      let attrsHtml = '';
      for (const attr of node.attributes) {{
        attrsHtml += ` <span class="tree-attr">${{attr.name}}=</span><span class="tree-val">"${{escapeHtml(attr.value)}}"</span>`;
      }}

      let childrenHtml = '';
      if (hasChildren) {{
        childrenHtml = Array.from(node.children).map(child => renderTreeNode(child)).join('');
      }}

      return `
        <div class="tree-node">
          <div class="tree-node-header" onclick="toggleTree(this)">
            <span class="tree-toggle">${{hasChildren ? '▼' : '•'}}</span>
            <span class="tree-tag">&lt;${{node.tagName}}</span>${{attrsHtml}}<span class="tree-tag">&gt;</span>
            ${{text ? `<span class="tree-text">${{escapeHtml(text.slice(0, 120))}}${{text.length > 120 ? '...' : ''}}</span>` : ''}}
          </div>
          ${{hasChildren ? `<div class="tree-children">${{childrenHtml}}</div>` : ''}}
        </div>
      `;
    }}

    function toggleTree(header) {{
      const children = header.nextElementSibling;
      const toggle = header.querySelector('.tree-toggle');
      if (children) {{
        if (children.style.display === 'none') {{
          children.style.display = 'block';
          toggle.textContent = '▼';
        }} else {{
          children.style.display = 'none';
          toggle.textContent = '▶';
        }}
      }}
    }}

    function setupTreeToggles() {{
      // Tree toggle listeners attached via inline onclick
    }}

    function setupTaskFilters() {{
      document.querySelectorAll('.filter-btn').forEach(btn => {{
        btn.addEventListener('click', () => {{
          document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          const filter = btn.getAttribute('data-filter');
          document.querySelectorAll('.task-card').forEach(card => {{
            const st = card.getAttribute('data-status');
            if (filter === 'all' || st === filter) {{
              card.style.display = 'block';
            }} else {{
              card.style.display = 'none';
            }}
          }});
        }});
      }});
    }}

    function escapeHtml(str) {{
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }}
  </script>
</body>
</html>
"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_template)

    print(f"Generated standalone visualizer: {output_file} ({output_file.stat().st_size:,} bytes)")
    return output_file


if __name__ == "__main__":
    workspace = Path(__file__).resolve().parent.parent.parent
    out = workspace / "visualizer.html"
    build_standalone_html(workspace, out)
