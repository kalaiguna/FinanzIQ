"""
Start a local HTTP server and open the FinanzIQ dashboard in your browser.

Usage:
    python launch.py          # default port 8080
    python launch.py 9000     # custom port
"""

import http.server
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).parent
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress per-request noise


def serve():
    os.chdir(ROOT)
    with http.server.HTTPServer(('', PORT), QuietHandler) as httpd:
        print(f"Serving at http://localhost:{PORT}")
        print(f"Dashboard: http://localhost:{PORT}/dashboard/index.html")
        print("Press Ctrl+C to stop.\n")
        httpd.serve_forever()


if __name__ == '__main__':
    t = threading.Thread(target=serve, daemon=True)
    t.start()

    # Small delay so the server is ready before the browser opens
    time.sleep(0.3)
    webbrowser.open(f'http://localhost:{PORT}/dashboard/index.html')

    try:
        t.join()
    except KeyboardInterrupt:
        print("\nServer stopped.")
