#!/usr/bin/env python3
"""
RoWorks AI Omniverse Web Server
Serves the mesh upload interface on port 49100
Simplified workflow: Mesh ZIP (mandatory) + optional assets
"""

import http.server
import socketserver
import os
import sys
import json
import urllib.parse
from pathlib import Path

# Configuration
PORT = 49100
DIRECTORY = "web"  # Directory containing your HTML files
API_PORT = 49101  # RoWorks API port

class RoWorksHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)
    
    def end_headers(self):
        # Add CORS headers for API communication
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, DELETE')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests with custom routing"""
        parsed_path = urllib.parse.urlparse(self.path)
        
        # API status endpoint for debugging
        if parsed_path.path == '/api/status':
            self.handle_api_status()
            return
        
        # Health check endpoint
        if parsed_path.path == '/health':
            self.handle_health_check()
            return
        
        # Serve static files normally
        super().do_GET()
    
    def handle_api_status(self):
        """Provide API connection status"""
        try:
            import requests
            response = requests.get(f'http://localhost:{API_PORT}/health', timeout=5)
            api_data = response.json()
            
            status_data = {
                "web_server": {
                    "status": "running",
                    "port": PORT,
                    "directory": DIRECTORY
                },
                "api_server": {
                    "status": "connected",
                    "port": API_PORT,
                    "service": api_data.get("service", "unknown"),
                    "version": api_data.get("version", "unknown"),
                    "workflow": api_data.get("workflow", "unknown")
                },
                "workflow": "Mesh ZIP (OBJ+MTL+textures) → USD creation → Scene import"
            }
            
        except Exception as e:
            status_data = {
                "web_server": {
                    "status": "running",
                    "port": PORT,
                    "directory": DIRECTORY
                },
                "api_server": {
                    "status": "disconnected",
                    "port": API_PORT,
                    "error": str(e)
                },
                "workflow": "Waiting for RoWorks API connection"
            }
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(status_data, indent=2).encode())
    
    def handle_health_check(self):
        """Simple health check for the web server"""
        health_data = {
            "status": "healthy",
            "service": "roworks_web_server",
            "port": PORT,
            "api_endpoint": f"http://localhost:{API_PORT}",
            "workflow": "Simplified mesh upload workflow"
        }
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(health_data, indent=2).encode())

def check_api_connection():
    """Check if the RoWorks API is running"""
    try:
        import requests
        response = requests.get(f'http://localhost:{API_PORT}/health', timeout=3)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ RoWorks API is running:")
            print(f"   Service: {data.get('service', 'Unknown')}")
            print(f"   Version: {data.get('version', 'Unknown')}")
            print(f"   Workflow: {data.get('workflow', 'Unknown')}")
            return True
    except Exception as e:
        print(f"⚠️  RoWorks API not responding: {e}")
        print(f"   Make sure the RoWorks Omniverse app is running")
        return False
    return False

def main():
    """Start the web server"""
    print("=" * 60)
    print("🚀 RoWorks AI Omniverse Web Server")
    print("=" * 60)
    
    # Create web directory if it doesn't exist
    os.makedirs(DIRECTORY, exist_ok=True)
    
    # Check if index.html exists
    index_file = Path(DIRECTORY) / "index.html"
    if not index_file.exists():
        print(f"❌ No index.html found in {DIRECTORY}/")
        print(f"   Please ensure the updated HTML file is saved as {DIRECTORY}/index.html")
        print(f"   The file should contain the mesh upload interface")
        sys.exit(1)
    
    print(f"📁 Serving files from: {os.path.abspath(DIRECTORY)}")
    print(f"🌐 Web interface: http://localhost:{PORT}")
    print(f"🌐 External access: http://ec2-3-132-234-13.us-east-2.compute.amazonaws.com:{PORT}")
    print(f"🔗 API endpoint: http://localhost:{API_PORT}")
    
    # Check API connection
    print("\n🔍 Checking RoWorks API connection...")
    api_connected = check_api_connection()
    
    if not api_connected:
        print("\n⚠️  Warning: RoWorks API is not responding")
        print("   The web interface will work, but uploads will fail")
        print("   Start the RoWorks Omniverse application first")
    
    print("\n📋 Workflow Summary:")
    print("   1. Upload mesh ZIP file (OBJ + MTL + textures) - REQUIRED")
    print("   2. Automatic USD asset creation with materials")
    print("   3. Instant import into Omniverse scene")
    print("   4. Optional: Add point clouds or robot models")
    
    print(f"\n🎯 Features:")
    print("   • Drag & drop file upload")
    print("   • ZIP content analysis")
    print("   • Real-time progress tracking")
    print("   • Scene asset management")
    print("   • Automatic USD creation")
    
    # Start server
    try:
        with socketserver.TCPServer(("", PORT), RoWorksHTTPRequestHandler) as httpd:
            print(f"\n🟢 Server running on port {PORT}")
            print("   Press Ctrl+C to stop the server")
            print("=" * 60)
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped by user")
    except OSError as e:
        if e.errno == 48:  # Address already in use
            print(f"\n❌ Port {PORT} is already in use")
            print("   Either stop the existing server or change the PORT in this script")
        else:
            print(f"\n❌ Error starting server: {e}")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")

if __name__ == "__main__":
    main()
