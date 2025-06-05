#!/usr/bin/env python3
"""
Simple HTTP server to serve the RoWorks upload interface on port 49100
"""

import http.server
import socketserver
import os
import sys
from pathlib import Path

# Configuration
PORT = 49100
DIRECTORY = "web"  # Directory containing your HTML files

class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)
    
    def end_headers(self):
        # Add CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

def main():
    # Create web directory if it doesn't exist
    os.makedirs(DIRECTORY, exist_ok=True)
    
    # Check if index.html exists
    index_file = Path(DIRECTORY) / "index.html"
    if not index_file.exists():
        print(f"❌ No index.html found in {DIRECTORY}/")
        print(f"Please save the upload interface HTML as {DIRECTORY}/index.html")
        sys.exit(1)
    
    # Start server
    try:
        with socketserver.TCPServer(("", PORT), CustomHTTPRequestHandler) as httpd:
            print(f"🌐 Serving upload interface at http://localhost:{PORT}")
            print(f"🌐 External access: http://ec2-3-132-234-13.us-east-2.compute.amazonaws.com:{PORT}")
            print(f"📁 Serving files from: {os.path.abspath(DIRECTORY)}")
            print("Press Ctrl+C to stop the server")
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Server stopped")
    except Exception as e:
        print(f"❌ Error starting server: {e}")

if __name__ == "__main__":
    main()
