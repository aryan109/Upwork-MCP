"""
XML Visualizer Launcher
Usage:
  python visualizer.py            # Opens standalone visualizer.html directly in browser (0 server required)
  python visualizer.py --server   # Starts optional local Python HTTP daemon (port 8765)
  python visualizer.py --build    # Recompiles visualizer.html with latest XML snapshots
"""
from __future__ import annotations

import argparse
import sys
import time
import webbrowser
from pathlib import Path

from aryan_implementation.visualizer.build_standalone import build_standalone_html


def main():
    parser = argparse.ArgumentParser(description="XML Visualizer for Upwork MCP")
    parser.add_argument("--server", action="store_true", help="Start local HTTP server daemon instead of serverless mode")
    parser.add_argument("--build", action="store_true", help="Recompile visualizer.html snapshot")
    parser.add_argument("--port", type=int, default=8765, help="Port for server daemon (default: 8765)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface (default: 127.0.0.1)")

    args = parser.parse_args()
    workspace = Path(__file__).resolve().parent
    html_file = workspace / "visualizer.html"

    if args.build or not html_file.exists():
        print("Building standalone visualizer.html snapshot...")
        build_standalone_html(workspace, html_file)

    if args.server:
        from aryan_implementation.visualizer.server import start_server
        server, server_thread = start_server(port=args.port, host=args.host)
        url = f"http://{args.host}:{args.port}/"

        print("\n" + "=" * 60)
        print(f"🚀 Real-Time XML Visualizer server is running at: {url}")
        print("Watching all workspace .xml files for live modifications...")
        print("Press Ctrl+C to stop the server.")
        print("=" * 60 + "\n")

        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down server...")
            server.shutdown()
            sys.exit(0)
    else:
        # Serverless Mode (default): open visualizer.html directly via file protocol
        file_url = html_file.as_uri()
        print("\n" + "=" * 60)
        print(f"⚡ Opening Serverless XML Visualizer directly in your browser:")
        print(f"   {file_url}")
        print("   • Zero server running, zero open ports, zero background processes.")
        print("   • Uses File System Access API for 0-server live disk sync.")
        print("=" * 60 + "\n")
        webbrowser.open(file_url)


if __name__ == "__main__":
    main()
