"""
Live-reloading HTTP Server for XML Visualisation.
Serves web UI, JSON APIs, and Server-Sent Events (SSE) for real-time file updates.
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import queue
import socketserver
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .parser import parse_xml_file

logger = logging.getLogger("xml_visualizer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

WORKSPACE_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"


class EventBroadcaster:
    """Manages active SSE client connections and broadcasts file changes."""

    def __init__(self):
        self._clients: List[queue.Queue] = []
        self._lock = threading.Lock()

    def register(self) -> queue.Queue:
        q = queue.Queue(maxsize=50)
        with self._lock:
            self._clients.append(q)
        return q

    def unregister(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._clients:
                self._clients.remove(q)

    def broadcast(self, event_type: str, data: dict) -> None:
        payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        with self._lock:
            dead_clients = []
            for q in self._clients:
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    dead_clients.append(q)
            for dead in dead_clients:
                self._clients.remove(dead)


broadcaster = EventBroadcaster()


class FileWatcher(threading.Thread):
    """Monitors XML files in the workspace and broadcasts modifications."""

    def __init__(self, root_dir: Path, poll_interval: float = 0.5):
        super().__init__(daemon=True)
        self.root_dir = root_dir
        self.poll_interval = poll_interval
        self._file_mtimes: Dict[str, float] = {}
        self._running = True

    def scan_files(self) -> Dict[str, float]:
        mtimes = {}
        for p in self.root_dir.rglob("*.xml"):
            # Exclude .git and scratch
            if ".git" in p.parts:
                continue
            try:
                mtimes[str(p.relative_to(self.root_dir))] = p.stat().st_mtime
            except OSError:
                pass
        return mtimes

    def run(self) -> None:
        self._file_mtimes = self.scan_files()
        while self._running:
            time.sleep(self.poll_interval)
            current_mtimes = self.scan_files()
            # Check for modified or new files
            for relpath, mtime in current_mtimes.items():
                old_mtime = self._file_mtimes.get(relpath)
                if old_mtime is not None and mtime > old_mtime:
                    logger.info(f"Detected modification in: {relpath}")
                    broadcaster.broadcast(
                        "file_changed",
                        {"file": relpath, "action": "modified", "ts": datetime.now(timezone.utc).isoformat()},
                    )
                elif old_mtime is None:
                    logger.info(f"Detected new file: {relpath}")
                    broadcaster.broadcast(
                        "file_changed",
                        {"file": relpath, "action": "created", "ts": datetime.now(timezone.utc).isoformat()},
                    )
            # Check for deleted
            for relpath in list(self._file_mtimes.keys()):
                if relpath not in current_mtimes:
                    logger.info(f"Detected deleted file: {relpath}")
                    broadcaster.broadcast(
                        "file_changed",
                        {"file": relpath, "action": "deleted", "ts": datetime.now(timezone.utc).isoformat()},
                    )
            self._file_mtimes = current_mtimes


class VisualizerHTTPHandler(SimpleHTTPRequestHandler):
    """Custom request handler for visualizer APIs and SSE stream."""

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        if path == "/api/files":
            self.handle_api_files()
        elif path == "/api/xml":
            query = parse_qs(parsed_url.query)
            rel_file = query.get("file", [""])[0]
            self.handle_api_xml(rel_file)
        elif path == "/api/stream":
            self.handle_sse_stream()
        elif path == "/" or path == "/index.html":
            self.serve_static_file("index.html", "text/html; charset=utf-8")
        elif path.startswith("/static/"):
            filename = path.replace("/static/", "", 1)
            self.serve_static_file(filename)
        else:
            self.send_error(404, "Not Found")

    def handle_api_files(self) -> None:
        files = []
        for p in WORKSPACE_DIR.rglob("*.xml"):
            if ".git" in p.parts:
                continue
            try:
                rel = str(p.relative_to(WORKSPACE_DIR)).replace("\\", "/")
                stat = p.stat()
                files.append({
                    "name": p.name,
                    "relpath": rel,
                    "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    "category": (
                        "Implementation Plan" if "implementation_plan" in p.name.lower() else
                        "MCP Documentation" if "mcp" in p.name.lower() else
                        "Comparative Analysis" if "comparative" in p.name.lower() else
                        "Strategy Overhaul" if "overhaul" in p.name.lower() or "strategy" in p.name.lower() else
                        "General XML"
                    ),
                })
            except OSError:
                pass

        files.sort(key=lambda x: (x["category"] != "Implementation Plan", x["name"]))
        self.send_json_response({"files": files})

    def handle_api_xml(self, rel_file: str) -> None:
        if not rel_file:
            self.send_json_response({"ok": False, "error": "file parameter required"}, status=400)
            return

        target_path = (WORKSPACE_DIR / rel_file).resolve()
        # Path traversal guard
        if not str(target_path).startswith(str(WORKSPACE_DIR.resolve())):
            self.send_json_response({"ok": False, "error": "Access denied"}, status=403)
            return

        if not target_path.exists():
            self.send_json_response({"ok": False, "error": f"File not found: {rel_file}"}, status=404)
            return

        parsed = parse_xml_file(target_path)
        self.send_json_response(parsed)

    def handle_sse_stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q = broadcaster.register()
        try:
            # Send initial ping
            init_msg = f"event: connected\ndata: {json.dumps({'status': 'connected', 'time': datetime.now(timezone.utc).isoformat()})}\n\n"
            self.wfile.write(init_msg.encode("utf-8"))
            self.wfile.flush()

            while True:
                try:
                    msg = q.get(timeout=20.0)
                    self.wfile.write(msg.encode("utf-8"))
                    self.wfile.flush()
                except queue.Empty:
                    # Keep-alive heartbeat comment
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            broadcaster.unregister(q)

    def serve_static_file(self, filename: str, content_type: Optional[str] = None) -> None:
        file_path = (STATIC_DIR / filename).resolve()
        if not file_path.exists() or not str(file_path).startswith(str(STATIC_DIR.resolve())):
            self.send_error(404, "Static file not found")
            return

        if not content_type:
            content_type, _ = mimetypes.guess_type(str(file_path))
            content_type = content_type or "application/octet-stream"

        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Error reading file: {e}")

    def send_json_response(self, data: Any, status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress routine GET logging for SSE ping
        if "/api/stream" in args[0] if args else False:
            return
        logger.debug("%s - - [%s] %s" % (self.client_address[0], self.log_date_time_string(), format % args))


class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_server(port: int = 8765, host: str = "127.0.0.1") -> Tuple[ThreadedHTTPServer, threading.Thread]:
    """Start the file watcher and threaded HTTP server."""
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    watcher = FileWatcher(WORKSPACE_DIR)
    watcher.start()

    server = ThreadedHTTPServer((host, port), VisualizerHTTPHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    logger.info(f"XML Visualizer server running at http://{host}:{port}/")
    return server, server_thread
