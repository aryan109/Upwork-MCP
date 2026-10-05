"""
Real-Time XML Visualizer Launcher
Usage:
  python visualizer.py [--port 8765] [--open]
"""
from __future__ import annotations

import argparse
import sys
import time
import webbrowser

from aryan_implementation.visualizer.server import start_server


def main():
    parser = argparse.ArgumentParser(description="Real-Time XML Visualizer for Upwork MCP")
    parser.add_argument("--port", type=int, default=8765, help="Port to run the HTTP server on (default: 8765)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    parser.add_argument("--open", action="store_true", default=True, help="Automatically open visualizer in default browser")
    parser.add_argument("--no-open", dest="open", action="store_false", help="Do not open browser automatically")

    args = parser.parse_args()

    server, server_thread = start_server(port=args.port, host=args.host)
    url = f"http://{args.host}:{args.port}/"

    print("\n" + "=" * 60)
    print(f"🚀 Real-Time XML Visualizer is running at: {url}")
    print("Watching all workspace .xml files for live modifications...")
    print("Press Ctrl+C to stop the server.")
    print("=" * 60 + "\n")

    if args.open:
        webbrowser.open(url)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down XML Visualizer server...")
        server.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()
