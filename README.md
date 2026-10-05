# Upwork Model Context Protocol (MCP)

Official documentation, capability matrix, and automated job proposal blueprints for the **Upwork MCP Server**.

## 📖 Documentation Formats

Comprehensive documentation has been generated in two formats:

- 📄 **[Markdown Documentation (UPWORK_MCP_DOCUMENTATION.md)](./UPWORK_MCP_DOCUMENTATION.md)**: Human-readable guide containing architecture diagrams, 51-tool capability matrix, end-to-end proposal automation walkthrough, Connects boost bidding strategy, pre-submission checks (avoiding error `VJ-JA-10`), and Python automation recipes.
- 🏷️ **[XML Documentation (UPWORK_MCP_DOCUMENTATION.xml)](./UPWORK_MCP_DOCUMENTATION.xml)**: Machine-readable structured specification containing protocol definitions, safety governance rules, granular input schemas, automated workflow stages, and complete platform error catalogs.

---

## 🚀 Key Highlights & Proposal Automation

### 1. Two-Phase "Draft-and-Confirm" Safety Pattern
All write operations (`create` proposal, `post_job`, profile edits) return a server-side preview with a `preview_id`. The action is staged and executed only when `upwork__confirm_preview` is called.

### 2. Proposal Hunting Workflow
1. **Discover**: Call `upwork__find_jobs` with `action="smart_search"` and `mode="most_recent"` (`days_posted=1`).
2. **Vet**: Inspect `find_jobs` `action="get"` to analyze client hiring rate, total spend, rating, and freelancer reviews for client contact names.
3. **Validate**: Check `upwork__list_freelancer_proposals` `invitations` and `list` to prevent conflicting submissions.
4. **Draft**: Call `upwork__manage_proposals` `action="create"` with personalized cover letter, answers to screening questions, and optimal Connects boost bid.
5. **Confirm**: Confirm via `upwork__confirm_preview` with `preview_id` after human operator approval.

---

## ⚡ Serverless XML Visualizer (`visualizer.html`)

An interactive, zero-server visualizer for exploring all workspace XML files (implementation plans, MCP protocols, and comparative evaluations):

- **Zero-Server Instant Launch**: Double-click [`visualizer.html`](./visualizer.html) or open it directly in any browser (`file:///...`). No Python daemon, open ports, or web server needed.
- **Embedded Snapshot**: Pre-packaged with all 11 workspace XML models, rendering dashboards and interactive DOM trees instantly on load.
- **0-Server Live Disk Sync**: Click *"🟢 Enable Live Disk Watch"* to grant one-time read access to the workspace folder via the Web File System Access API. The browser polls file timestamps every 1 second and re-renders live in real time when files change on disk.
- **Drag & Drop**: Drop any external XML file directly onto the browser window.
- **Optional CLI Launcher**:
  ```powershell
  python visualizer.py            # Opens visualizer.html directly in browser
  python visualizer.py --server   # Starts optional local HTTP daemon (port 8765)
  python visualizer.py --build    # Recompiles visualizer.html with latest XML snapshots
  ```

---

## 🛠️ Project Logs
Detailed execution logs and changes are tracked in [project_development_logs.md](./project_development_logs.md).

