#!/usr/bin/env python3
"""
Fixed RoWorks Web Server - Handles SSL attempts gracefully
"""

import http.server
import socketserver
import os
import sys
import json
import urllib.parse
import socket
import ssl
from pathlib import Path

# Configuration
PORT = 49100
DIRECTORY = "web"
API_PORT = 49101

def get_server_info():
    """Get server hostname and IP information"""
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except:
        local_ip = "127.0.0.1"
    
    is_aws = hostname.startswith('ip-') or 'ec2' in hostname.lower()
    
    return {
        "hostname": hostname,
        "local_ip": local_ip,
        "is_aws": is_aws,
        "public_hostname": "ec2-3-132-234-13.us-east-2.compute.amazonaws.com" if is_aws else hostname
    }

class FixedRoWorksHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Fixed HTTP handler that gracefully handles SSL attempts"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)
    
    def parse_request(self):
        """Override to handle SSL attempts gracefully"""
        try:
            return super().parse_request()
        except Exception as e:
            # Check if this looks like an SSL handshake
            if hasattr(self, 'raw_requestline') and self.raw_requestline:
                if self.raw_requestline.startswith(b'\x16\x03'):
                    # This is an SSL handshake attempt
                    self.send_error(400, "SSL/HTTPS not supported. Use HTTP instead.")
                    return False
            
            # Other parsing errors
            self.send_error(400, "Bad request")
            return False
    
    def log_request(self, code='-', size='-'):
        """Custom logging to suppress SSL errors"""
        if isinstance(code, int) and code == 400:
            # Don't log detailed SSL errors, just note the attempt
            print(f"⚠️ SSL/HTTPS attempt blocked - use HTTP instead")
        else:
            super().log_request(code, size)
    
    def end_headers(self):
        # Add CORS headers
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
        
        if parsed_path.path == '/server-info':
            self.handle_server_info()
            return
        
        if parsed_path.path == '/health':
            self.handle_health_check()
            return
        
        if parsed_path.path == '/api/status':
            self.handle_api_status()
            return
        
        # Serve static files normally
        super().do_GET()
    
    def handle_server_info(self):
        """Provide server information"""
        server_info = get_server_info()
        
        api_urls = []
        if server_info["is_aws"]:
            api_urls = [
                f"http://{server_info['public_hostname']}:{API_PORT}",
                f"http://{server_info['local_ip']}:{API_PORT}",
                f"http://localhost:{API_PORT}",
                f"http://127.0.0.1:{API_PORT}"
            ]
        else:
            api_urls = [
                f"http://localhost:{API_PORT}",
                f"http://127.0.0.1:{API_PORT}",
                f"http://{server_info['local_ip']}:{API_PORT}"
            ]
        
        response_data = {
            "server_info": server_info,
            "suggested_api_urls": api_urls,
            "deployment_type": "aws_ec2" if server_info["is_aws"] else "local",
            "ssl_note": "Use HTTP only - SSL/HTTPS not supported"
        }
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response_data, indent=2).encode())
    
    def handle_api_status(self):
        """Check API status"""
        try:
            import requests
            server_info = get_server_info()
            
            if server_info["is_aws"]:
                api_urls = [
                    f"http://{server_info['public_hostname']}:{API_PORT}/health",
                    f"http://{server_info['local_ip']}:{API_PORT}/health",
                    f"http://localhost:{API_PORT}/health"
                ]
            else:
                api_urls = [
                    f"http://localhost:{API_PORT}/health",
                    f"http://127.0.0.1:{API_PORT}/health"
                ]
            
            api_data = None
            working_url = None
            
            for url in api_urls:
                try:
                    response = requests.get(url, timeout=5)
                    if response.status_code == 200:
                        api_data = response.json()
                        working_url = url
                        break
                except:
                    continue
            
            if api_data and working_url:
                status_data = {
                    "web_server": {
                        "status": "running",
                        "port": PORT,
                        "ssl_support": False,
                        "protocol": "HTTP only"
                    },
                    "api_server": {
                        "status": "connected",
                        "url": working_url,
                        "service": api_data.get("service", "unknown"),
                        "version": api_data.get("version", "unknown")
                    }
                }
            else:
                status_data = {
                    "web_server": {
                        "status": "running", 
                        "port": PORT,
                        "ssl_support": False
                    },
                    "api_server": {
                        "status": "disconnected",
                        "tried_urls": api_urls
                    }
                }
            
        except Exception as e:
            status_data = {
                "web_server": {"status": "running", "port": PORT},
                "api_server": {"status": "error", "error": str(e)}
            }
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(status_data, indent=2).encode())
    
    def handle_health_check(self):
        """Web server health check"""
        server_info = get_server_info()
        
        health_data = {
            "status": "healthy",
            "service": "roworks_web_server_fixed",
            "port": PORT,
            "protocol": "HTTP",
            "ssl_support": False,
            "deployment": "aws_ec2" if server_info["is_aws"] else "local",
            "fixes": [
                "SSL attempts handled gracefully",
                "No more SSL handshake errors",
                "Proper error responses for HTTPS attempts"
            ]
        }
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(health_data, indent=2).encode())

def main():
    """Start the fixed web server"""
    server_info = get_server_info()
    
    print("=" * 60)
    print("🚀 RoWorks Fixed Web Server")
    print("=" * 60)
    
    print(f"🌐 Deployment: {'AWS EC2' if server_info['is_aws'] else 'Local'}")
    print(f"🖥️  Hostname: {server_info['hostname']}")
    print(f"📡 Local IP: {server_info['local_ip']}")
    
    # Create web directory
    os.makedirs(DIRECTORY, exist_ok=True)
    
    print(f"📁 Serving from: {os.path.abspath(DIRECTORY)}")
    print(f"🌐 Web interface: http://localhost:{PORT}")
    
    if server_info["is_aws"]:
        print(f"🌍 Public access: http://{server_info['public_hostname']}:{PORT}")
    
    print("\\n🔧 FIXES APPLIED:")
    print("   ✅ SSL/HTTPS attempts handled gracefully")
    print("   ✅ No more SSL handshake error messages")
    print("   ✅ Proper 400 Bad Request for SSL attempts")
    print("   ✅ Simplified error logging")
    
    print("\\n⚠️  IMPORTANT:")
    print("   • Use HTTP only (not HTTPS)")
    print("   • SSL/TLS is not supported")
    print("   • Browser may try HTTPS first - that's normal")
    
    # Start server with custom handler
    try:
        with socketserver.TCPServer(("", PORT), FixedRoWorksHTTPRequestHandler) as httpd:
            print(f"\\n🟢 Fixed server running on port {PORT}")
            print("   SSL attempts will be handled gracefully")
            print("   Press Ctrl+C to stop")
            print("=" * 60)
            httpd.serve_forever()
            
    except KeyboardInterrupt:
        print("\\n\\n👋 Server stopped by user")
    except OSError as e:
        if e.errno == 48 or e.errno == 98:  # Address already in use
            print(f"\\n❌ Port {PORT} is already in use")
            print("   Stop the existing server or change the PORT")
        else:
            print(f"\\n❌ Server error: {e}")
    except Exception as e:
        print(f"\\n❌ Unexpected error: {e}")

if __name__ == "__main__":
    main()
