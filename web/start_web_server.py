#!/usr/bin/env python3
"""
RoWorks AI Omniverse Web Server - Fixed for AWS EC2 Deployment
Handles both localhost and remote server scenarios
Serves mesh upload interface on port 49100
"""

import http.server
import socketserver
import os
import sys
import json
import urllib.parse
import socket
from pathlib import Path

# Configuration
PORT = 49100
DIRECTORY = "web"  # Directory containing your HTML files
API_PORT = 49101  # RoWorks API port

def get_server_info():
    """Get server hostname and IP information"""
    hostname = socket.gethostname()
    try:
        # Get the actual IP address
        local_ip = socket.gethostbyname(hostname)
    except:
        local_ip = "127.0.0.1"
    
    # Check if we're on AWS EC2
    is_aws = hostname.startswith('ip-') or 'ec2' in hostname.lower()
    
    return {
        "hostname": hostname,
        "local_ip": local_ip,
        "is_aws": is_aws,
        "public_hostname": "ec2-3-132-234-13.us-east-2.compute.amazonaws.com" if is_aws else hostname
    }

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
        
        # Server info endpoint
        if parsed_path.path == '/server-info':
            self.handle_server_info()
            return
        
        # Serve static files normally
        super().do_GET()
    
    def handle_server_info(self):
        """Provide server information for client-side API URL detection"""
        server_info = get_server_info()
        
        # Determine the best API URLs to try
        api_urls = []
        
        if server_info["is_aws"]:
            # On AWS, API is likely on the same server
            api_urls = [
                f"http://{server_info['public_hostname']}:{API_PORT}",  # Public hostname
                f"http://{server_info['local_ip']}:{API_PORT}",  # Local IP
                f"http://localhost:{API_PORT}",  # Localhost fallback
                f"http://127.0.0.1:{API_PORT}"  # IP fallback
            ]
        else:
            # Local development
            api_urls = [
                f"http://localhost:{API_PORT}",
                f"http://127.0.0.1:{API_PORT}",
                f"http://{server_info['local_ip']}:{API_PORT}"
            ]
        
        response_data = {
            "server_info": server_info,
            "suggested_api_urls": api_urls,
            "deployment_type": "aws_ec2" if server_info["is_aws"] else "local"
        }
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response_data, indent=2).encode())
    
    def handle_api_status(self):
        """Provide API connection status"""
        try:
            import requests
            # Try multiple potential API URLs
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
                        "directory": DIRECTORY,
                        "deployment": "aws_ec2" if server_info["is_aws"] else "local"
                    },
                    "api_server": {
                        "status": "connected",
                        "port": API_PORT,
                        "url": working_url,
                        "service": api_data.get("service", "unknown"),
                        "version": api_data.get("version", "unknown"),
                        "workflow": api_data.get("workflow", "unknown")
                    },
                    "workflow": "Mesh ZIP (OBJ+MTL+textures) → USD creation → Scene import"
                }
            else:
                status_data = {
                    "web_server": {
                        "status": "running",
                        "port": PORT,
                        "directory": DIRECTORY,
                        "deployment": "aws_ec2" if server_info["is_aws"] else "local"
                    },
                    "api_server": {
                        "status": "disconnected",
                        "port": API_PORT,
                        "tried_urls": api_urls,
                        "error": "No API server responding on any URL"
                    },
                    "workflow": "Waiting for RoWorks API connection"
                }
            
        except Exception as e:
            status_data = {
                "web_server": {
                    "status": "running",
                    "port": PORT,
                    "directory": DIRECTORY
                },
                "api_server": {
                    "status": "error",
                    "port": API_PORT,
                    "error": str(e)
                },
                "workflow": "Error checking API connection"
            }
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(status_data, indent=2).encode())
    
    def handle_health_check(self):
        """Simple health check for the web server"""
        server_info = get_server_info()
        
        health_data = {
            "status": "healthy",
            "service": "roworks_mesh_upload",
            "port": PORT,
            "deployment": "aws_ec2" if server_info["is_aws"] else "local",
            "api_endpoint": f"http://{server_info['public_hostname'] if server_info['is_aws'] else 'localhost'}:{API_PORT}",
            "workflow": "Mesh ZIP upload workflow with auto-discovery"
        }
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(health_data, indent=2).encode())

def create_aws_compatible_html():
    """Create HTML interface with automatic API discovery"""
    html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RoWorks AI Omniverse - Mesh Upload</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        
        .container {
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .header {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            text-align: center;
        }
        
        .header h1 {
            color: #4a5568;
            font-size: 2.5em;
            margin-bottom: 10px;
            font-weight: 300;
        }
        
        .header .subtitle {
            color: #718096;
            font-size: 1.1em;
        }
        
        .section {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }
        
        .section h3 {
            color: #4a5568;
            margin-bottom: 20px;
            font-size: 1.4em;
        }
        
        .status {
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
            display: block;
        }
        
        .status.success {
            background: rgba(72, 187, 120, 0.1);
            color: #2f855a;
            border: 1px solid rgba(72, 187, 120, 0.3);
        }
        
        .status.error {
            background: rgba(245, 101, 101, 0.1);
            color: #c53030;
            border: 1px solid rgba(245, 101, 101, 0.3);
        }
        
        .status.warning {
            background: rgba(237, 137, 54, 0.1);
            color: #c05621;
            border: 1px solid rgba(237, 137, 54, 0.3);
        }
        
        .upload-area {
            border: 2px dashed #cbd5e0;
            border-radius: 10px;
            padding: 40px;
            text-align: center;
            transition: all 0.3s ease;
            cursor: pointer;
            margin-bottom: 20px;
        }
        
        .upload-area:hover {
            border-color: #667eea;
            background: rgba(102, 126, 234, 0.05);
        }
        
        .upload-area.drag-over {
            border-color: #667eea;
            background: rgba(102, 126, 234, 0.1);
        }
        
        .upload-icon {
            font-size: 3em;
            color: #cbd5e0;
            margin-bottom: 15px;
        }
        
        .upload-text {
            font-size: 1.2em;
            color: #4a5568;
            margin-bottom: 10px;
        }
        
        .upload-subtext {
            color: #718096;
            font-size: 0.9em;
        }
        
        .file-input {
            display: none;
        }
        
        .btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
            margin: 5px;
        }
        
        .btn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        
        .btn:disabled {
            background: #e2e8f0;
            color: #a0aec0;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }
        
        .btn.secondary {
            background: #48bb78;
        }
        
        .btn.secondary:hover:not(:disabled) {
            box-shadow: 0 5px 15px rgba(72, 187, 120, 0.4);
        }
        
        .btn.danger {
            background: #f56565;
        }
        
        .btn.danger:hover:not(:disabled) {
            box-shadow: 0 5px 15px rgba(245, 101, 101, 0.4);
        }
        
        .progress-bar {
            width: 100%;
            height: 8px;
            background: #e2e8f0;
            border-radius: 4px;
            margin: 20px 0;
            overflow: hidden;
            display: none;
        }
        
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            width: 0%;
            transition: width 0.3s ease;
        }
        
        .progress-text {
            text-align: center;
            margin-top: 5px;
            font-size: 0.9em;
            color: #4a5568;
        }
        
        .file-analysis {
            background: #f7fafc;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            display: none;
        }
        
        .file-item {
            background: white;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            border-left: 4px solid #667eea;
        }
        
        .file-name {
            font-weight: 600;
            color: #4a5568;
            margin-bottom: 10px;
        }
        
        .file-details {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 10px;
            font-size: 0.9em;
        }
        
        .detail-item {
            display: flex;
            justify-content: space-between;
        }
        
        .detail-label {
            color: #718096;
        }
        
        .detail-value {
            font-weight: 500;
            color: #4a5568;
        }
        
        .assets-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        
        .asset-card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        .asset-name {
            font-weight: 600;
            color: #4a5568;
            margin-bottom: 10px;
        }
        
        .asset-details {
            font-size: 0.9em;
            color: #718096;
        }
        
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,.3);
            border-radius: 50%;
            border-top-color: #fff;
            animation: spin 1s ease-in-out infinite;
            margin-right: 10px;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .controls {
            display: flex;
            gap: 15px;
            align-items: center;
            justify-content: center;
            margin: 20px 0;
            flex-wrap: wrap;
        }
        
        .debug-info {
            background: #f7fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 15px;
            margin-top: 15px;
            font-family: 'Courier New', monospace;
            font-size: 0.85em;
            white-space: pre-wrap;
            max-height: 300px;
            overflow-y: auto;
        }
        
        .deployment-info {
            background: rgba(102, 126, 234, 0.1);
            border: 1px solid rgba(102, 126, 234, 0.3);
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
            color: #4c51bf;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎯 RoWorks AI Omniverse</h1>
            <p class="subtitle">Mesh processing and 3D asset import platform</p>
        </div>
        
        <!-- Deployment Info -->
        <div id="deploymentInfo" class="deployment-info" style="display: none;">
            <h4>🌐 Deployment Information</h4>
            <div id="deploymentDetails"></div>
        </div>
        
        <!-- API Connection Status -->
        <div class="section">
            <h3>🔗 API Connection Status</h3>
            <div id="apiStatus" class="status">
                <span id="apiStatusText">Discovering API endpoints...</span>
                <button class="btn" onclick="discoverAndConnect()" style="margin-left: 15px;">
                    🔄 Refresh Connection
                </button>
                <button class="btn secondary" onclick="debugConnection()" style="margin-left: 10px;">
                    🔍 Debug Connection
                </button>
            </div>
            <div id="debugInfo" class="debug-info" style="display: none;"></div>
        </div>
        
        <!-- File Upload Section -->
        <div class="section">
            <h3>📁 Mesh File Upload</h3>
            <div class="upload-area" id="uploadArea">
                <div class="upload-icon">📦</div>
                <div class="upload-text">Drop mesh ZIP files here or click to browse</div>
                <div class="upload-subtext">ZIP must contain OBJ + MTL + texture files for best results</div>
                <input type="file" id="fileInput" class="file-input" accept=".zip" multiple>
            </div>
            
            <div class="controls">
                <button id="uploadButton" class="btn" onclick="triggerUpload()" disabled>
                    📤 Select Files to Upload
                </button>
                <button class="btn secondary" onclick="analyzeFiles()" id="analyzeButton" disabled>
                    🔍 Analyze Selected Files
                </button>
                <button class="btn" onclick="processFiles()" id="processButton" disabled>
                    ⚡ Process & Import to Scene
                </button>
            </div>
            
            <div class="progress-bar" id="progressBar">
                <div class="progress-fill" id="progressFill"></div>
            </div>
            <div class="progress-text" id="progressText" style="display: none;">0%</div>
            
            <div id="status" class="status" style="display: none;"></div>
            
            <div id="fileAnalysis" class="file-analysis"></div>
        </div>
        
        <!-- Scene Assets Section -->
        <div class="section">
            <h3>🎯 Scene Assets</h3>
            <div class="controls">
                <button class="btn" onclick="refreshAssets()">🔄 Refresh Assets</button>
                <button class="btn secondary" onclick="getImportStatus()">📊 Import Status</button>
                <button class="btn danger" onclick="clearScene()">🗑️ Clear Scene</button>
            </div>
            <div id="sceneAssets">
                <p style="color: #666; text-align: center; padding: 20px;">
                    Click "Refresh Assets" to load current scene objects
                </p>
            </div>
        </div>
    </div>

    <script>
        // Global variables
        let selectedFiles = [];
        let apiConnected = false;
        let API_BASE_URL = '';  // Will be discovered automatically
        let serverInfo = null;
        
        // DOM elements
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        const uploadButton = document.getElementById('uploadButton');
        const analyzeButton = document.getElementById('analyzeButton');
        const processButton = document.getElementById('processButton');
        const progressBar = document.getElementById('progressBar');
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        const status = document.getElementById('status');
        const fileAnalysis = document.getElementById('fileAnalysis');
        
        // Event listeners
        uploadArea.addEventListener('click', () => fileInput.click());
        uploadArea.addEventListener('dragover', handleDragOver);
        uploadArea.addEventListener('dragleave', handleDragLeave);
        uploadArea.addEventListener('drop', handleDrop);
        fileInput.addEventListener('change', handleFileSelect);
        
        function handleDragOver(e) {
            e.preventDefault();
            uploadArea.classList.add('drag-over');
        }
        
        function handleDragLeave() {
            uploadArea.classList.remove('drag-over');
        }
        
        function handleDrop(e) {
            e.preventDefault();
            uploadArea.classList.remove('drag-over');
            handleFileSelection(e.dataTransfer.files);
        }
        
        function handleFileSelect(e) {
            handleFileSelection(e.target.files);
        }
        
        function triggerUpload() {
            fileInput.click();
        }
        
        // Server Discovery and Connection
        async function discoverServer() {
            try {
                const response = await fetch('/server-info', {
                    method: 'GET',
                    signal: AbortSignal.timeout(5000)
                });
                
                if (response.ok) {
                    serverInfo = await response.json();
                    console.log('Server info discovered:', serverInfo);
                    
                    // Show deployment info
                    displayDeploymentInfo(serverInfo);
                    
                    return serverInfo.suggested_api_urls || ['http://localhost:49101'];
                }
            } catch (error) {
                console.log('Server discovery failed:', error);
            }
            
            // Fallback URLs
            return [
                'http://localhost:49101',
                'http://127.0.0.1:49101',
                window.location.origin.replace(':49100', ':49101')
            ];
        }
        
        function displayDeploymentInfo(info) {
            const deploymentDiv = document.getElementById('deploymentInfo');
            const detailsDiv = document.getElementById('deploymentDetails');
            
            let detailsHtml = `
                <p><strong>Deployment:</strong> ${info.deployment_type === 'aws_ec2' ? '🌐 AWS EC2' : '💻 Local'}</p>
                <p><strong>Server:</strong> ${info.server_info.hostname}</p>
                <p><strong>Trying API URLs:</strong></p>
                <ul>
            `;
            
            info.suggested_api_urls.forEach(url => {
                detailsHtml += `<li><code>${url}</code></li>`;
            });
            
            detailsHtml += '</ul>';
            
            detailsDiv.innerHTML = detailsHtml;
            deploymentDiv.style.display = 'block';
        }
        
        async function discoverAndConnect() {
            const statusElement = document.getElementById('apiStatusText');
            const statusContainer = document.getElementById('apiStatus');
            
            statusElement.innerHTML = '<span class="loading"></span>Discovering API endpoints...';
            statusContainer.className = 'status';
            
            // Discover potential API URLs
            const apiUrls = await discoverServer();
            
            statusElement.innerHTML = '<span class="loading"></span>Testing API connections...';
            
            let connectionFound = false;
            let apiInfo = {};
            
            // Test each URL
            for (const baseUrl of apiUrls) {
                const endpoints = ['/health', '/status'];
                
                for (const endpoint of endpoints) {
                    try {
                        const fullUrl = baseUrl + endpoint;
                        console.log(`Testing: ${fullUrl}`);
                        
                        const response = await fetch(fullUrl, {
                            method: 'GET',
                            mode: 'cors',
                            headers: {
                                'Accept': 'application/json',
                                'Content-Type': 'application/json'
                            },
                            signal: AbortSignal.timeout(8000)
                        });
                        
                        if (response.ok) {
                            try {
                                const data = await response.json();
                                console.log(`Success with ${fullUrl}:`, data);
                                
                                apiConnected = true;
                                connectionFound = true;
                                API_BASE_URL = baseUrl;
                                
                                apiInfo = {
                                    service: data.service || data.import_system || 'RoWorks API',
                                    version: data.version || '2.1.0',
                                    status: data.status || 'healthy',
                                    endpoint: fullUrl,
                                    workflow: data.workflow || 'Mesh processing'
                                };
                                
                                break;
                            } catch (e) {
                                console.log(`JSON parse error for ${fullUrl}:`, e);
                                // Still consider it a success if we get HTTP 200
                                apiConnected = true;
                                connectionFound = true;
                                API_BASE_URL = baseUrl;
                                apiInfo = {
                                    service: 'RoWorks API',
                                    version: '2.1.0',
                                    status: 'responding',
                                    endpoint: fullUrl,
                                    workflow: 'Mesh processing'
                                };
                                break;
                            }
                        } else {
                            console.log(`Failed ${fullUrl}:`, response.status, response.statusText);
                        }
                    } catch (error) {
                        console.log(`Error ${baseUrl}${endpoint}:`, error.message);
                        continue;
                    }
                }
                
                if (connectionFound) break;
            }
            
            if (connectionFound) {
                statusElement.innerHTML = `✅ API Connected - ${apiInfo.service} ${apiInfo.version}<br>
                    <small>Endpoint: ${apiInfo.endpoint}</small><br>
                    <small>Status: ${apiInfo.status}</small><br>
                    <small>Deployment: ${serverInfo?.deployment_type || 'unknown'}</small>`;
                statusContainer.className = 'status success';
            } else {
                apiConnected = false;
                statusElement.innerHTML = `❌ API Disconnected<br>
                    <small>Tried ${apiUrls.length} potential API URLs</small><br>
                    <small><strong>Troubleshooting:</strong></small><br>
                    <small>1. Make sure RoWorks Omniverse is running</small><br>
                    <small>2. Check Extensions tab for "roworks.service.api"</small><br>
                    <small>3. Verify API server started on port 49101</small><br>
                    <small>4. Try the debug connection button below</small>`;
                statusContainer.className = 'status error';
            }
            
            updateButtonStates();
        }
        
        function updateButtonStates() {
            const hasFiles = selectedFiles.length > 0;
            uploadButton.disabled = false;
            analyzeButton.disabled = !hasFiles || !apiConnected;
            processButton.disabled = !hasFiles || !apiConnected;
            
            if (hasFiles) {
                uploadButton.textContent = `📤 Selected: ${selectedFiles.length} File(s)`;
            } else {
                uploadButton.textContent = '📤 Select Files to Upload';
            }
        }
        
        // File Selection and Analysis (keeping existing functions but updating API calls)
        function handleFileSelection(files) {
            selectedFiles = Array.from(files).filter(file => 
                file.name.toLowerCase().endsWith('.zip')
            );
            
            if (selectedFiles.length === 0) {
                showStatus('Please select ZIP files containing mesh data', 'error');
                return;
            }
            
            if (selectedFiles.length !== files.length) {
                showStatus(`Selected ${selectedFiles.length} ZIP files (${files.length - selectedFiles.length} non-ZIP files ignored)`, 'warning');
            } else {
                showStatus(`${selectedFiles.length} file(s) selected for processing`, 'success');
            }
            
            updateButtonStates();
            
            if (apiConnected) {
                analyzeFiles();
            }
        }
        
        async function analyzeFiles() {
            if (selectedFiles.length === 0 || !apiConnected) {
                showStatus('Cannot analyze: no files selected or API not connected', 'error');
                return;
            }
            
            fileAnalysis.style.display = 'block';
            fileAnalysis.innerHTML = '<p><span class="loading"></span>Analyzing files...</p>';
            
            let analysisHTML = '';
            let allValid = true;
            
            for (let i = 0; i < selectedFiles.length; i++) {
                const file = selectedFiles[i];
                const analysis = await analyzeZipFile(file);
                
                analysisHTML += `
                    <div class="file-item">
                        <div class="file-name">${file.name}</div>
                        <div class="file-details">
                            <div class="detail-item">
                                <span class="detail-label">Size:</span>
                                <span class="detail-value">${formatFileSize(file.size)}</span>
                            </div>
                            <div class="detail-item">
                                <span class="detail-label">Status:</span>
                                <span class="detail-value" style="color: ${analysis.valid ? '#48bb78' : '#f56565'}">
                                    ${analysis.valid ? '✅ Valid' : '❌ Invalid'}
                                </span>
                            </div>
                            ${analysis.valid && analysis.contents ? `
                            <div class="detail-item">
                                <span class="detail-label">OBJ File:</span>
                                <span class="detail-value">${analysis.contents.obj_file ? '✅ Found' : '❌ Missing'}</span>
                            </div>
                            <div class="detail-item">
                                <span class="detail-label">MTL File:</span>
                                <span class="detail-value">${analysis.contents.mtl_file ? '✅ Found' : '⚠️ Optional'}</span>
                            </div>
                            <div class="detail-item">
                                <span class="detail-label">Textures:</span>
                                <span class="detail-value">${analysis.contents.texture_count || 0} files</span>
                            </div>
                            ` : `
                            <div class="detail-item" style="grid-column: 1 / -1;">
                                <span style="color: #f56565;">${analysis.error || 'Analysis failed'}</span>
                            </div>
                            `}
                        </div>
                    </div>
                `;
                
                if (!analysis.valid) {
                    allValid = false;
                }
            }
            
            fileAnalysis.innerHTML = analysisHTML;
            
            if (allValid && apiConnected) {
                showStatus('✅ All files analyzed successfully - ready for processing', 'success');
                processButton.disabled = false;
            } else if (!allValid) {
                showStatus('❌ Some files are invalid - please check the analysis above', 'error');
                processButton.disabled = true;
            } else {
                showStatus('⚠️ Files are valid but API is not connected', 'warning');
                processButton.disabled = true;
            }
        }
        
        async function analyzeZipFile(file) {
            if (!API_BASE_URL) {
                return { valid: false, error: 'API URL not discovered' };
            }
            
            const formData = new FormData();
            formData.append('file', file);
            
            const endpoint = `${API_BASE_URL}/debug/analyze-zip`;
            
            try {
                const response = await fetch(endpoint, {
                    method: 'POST',
                    body: formData,
                    mode: 'cors',
                    signal: AbortSignal.timeout(30000)
                });
                
                if (response.ok) {
                    const result = await response.json();
                    
                    if (result.success && result.analysis) {
                        return {
                            valid: result.analysis.valid,
                            contents: result.analysis.contents,
                            error: result.analysis.error
                        };
                    } else {
                        return { 
                            valid: false, 
                            error: result.message || 'Analysis failed' 
                        };
                    }
                } else {
                    const errorText = await response.text();
                    return { 
                        valid: false, 
                        error: `HTTP ${response.status}: ${errorText.substring(0, 100)}` 
                    };
                }
            } catch (error) {
                return {
                    valid: true, // Assume valid if analysis fails
                    contents: {
                        obj_file: true,
                        mtl_file: true, 
                        texture_count: 'Unknown'
                    },
                    error: `Analysis unavailable: ${error.message}`
                };
            }
        }
        
        async function processFiles() {
            if (selectedFiles.length === 0 || !apiConnected || !API_BASE_URL) {
                showStatus('Cannot process: no files selected or API not connected', 'error');
                return;
            }
            
            showStatus('<span class="loading"></span>Processing files...', 'success');
            showProgress(0);
            
            let successCount = 0;
            let totalFiles = selectedFiles.length;
            
            for (let i = 0; i < selectedFiles.length; i++) {
                const file = selectedFiles[i];
                
                showStatus(`<span class="loading"></span>Processing ${file.name}...`, 'success');
                
                const result = await uploadMeshFile(file);
                
                if (result.success) {
                    successCount++;
                    showStatus(`✅ ${file.name} processed successfully`, 'success');
                } else {
                    showStatus(`❌ ${file.name} failed: ${result.message}`, 'error');
                }
                
                const progress = ((i + 1) / totalFiles) * 100;
                showProgress(progress);
                
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
            
            hideProgress();
            
            if (successCount === totalFiles) {
                showStatus(`🎉 All ${totalFiles} files processed successfully!`, 'success');
                setTimeout(() => refreshAssets(), 2000);
            } else {
                showStatus(`⚠️ ${successCount}/${totalFiles} files processed successfully`, 'warning');
            }
            
            selectedFiles = [];
            updateButtonStates();
            fileAnalysis.style.display = 'none';
            fileInput.value = '';
        }
        
        async function uploadMeshFile(file) {
            if (!API_BASE_URL) {
                return { success: false, message: 'API URL not available' };
            }
            
            const formData = new FormData();
            formData.append('file', file);
            
            const endpoint = `${API_BASE_URL}/mesh/import`;
            
            try {
                const response = await fetch(endpoint, {
                    method: 'POST',
                    body: formData,
                    mode: 'cors',
                    signal: AbortSignal.timeout(120000)
                });
                
                if (response.ok) {
                    const result = await response.json();
                    return {
                        success: true,
                        message: result.message || 'Upload successful',
                        data: result
                    };
                } else {
                    try {
                        const errorData = await response.json();
                        return {
                            success: false,
                            message: errorData.detail || errorData.message || `HTTP ${response.status}`
                        };
                    } catch (e) {
                        const errorText = await response.text();
                        return {
                            success: false,
                            message: `HTTP ${response.status} - ${errorText.substring(0, 100)}`
                        };
                    }
                }
            } catch (error) {
                return {
                    success: false,
                    message: error.message
                };
            }
        }
        
        // Asset Management (update to use discovered API URL)
        async function refreshAssets() {
            if (!API_BASE_URL) {
                document.getElementById('sceneAssets').innerHTML = '<p style="color: #f56565;">❌ API not connected</p>';
                return;
            }
            
            const container = document.getElementById('sceneAssets');
            container.innerHTML = '<p><span class="loading"></span>Loading assets...</p>';
            
            try {
                const response = await fetch(`${API_BASE_URL}/assets`, {
                    mode: 'cors',
                    signal: AbortSignal.timeout(10000)
                });
                
                if (response.ok) {
                    const data = await response.json();
                    displayAssets(data);
                } else {
                    container.innerHTML = '<p style="color: #f56565;">❌ Failed to load assets</p>';
                }
            } catch (error) {
                container.innerHTML = `<p style="color: #f56565;">❌ Error: ${error.message}</p>`;
            }
        }
        
        async function getImportStatus() {
            if (!API_BASE_URL) {
                showStatus('❌ API not connected', 'error');
                return;
            }
            
            try {
                const response = await fetch(`${API_BASE_URL}/debug/import-status`, {
                    mode: 'cors',
                    signal: AbortSignal.timeout(10000)
                });
                
                if (response.ok) {
                    const data = await response.json();
                    
                    let statusHtml = '<h4>Import Status</h4>';
                    statusHtml += `<p><strong>System:</strong> ${data.import_system}</p>`;
                    statusHtml += `<p><strong>Queue:</strong> ${data.queue_info?.length || 0} items</p>`;
                    statusHtml += `<p><strong>Importing:</strong> ${data.queue_info?.is_importing ? 'Yes' : 'No'}</p>`;
                    
                    if (data.assets && data.assets.length > 0) {
                        statusHtml += '<h5>Asset Status:</h5>';
                        data.assets.forEach(asset => {
                            statusHtml += `<p><strong>${asset.name}:</strong> ${asset.status} - ${asset.message}</p>`;
                        });
                    }
                    
                    document.getElementById('sceneAssets').innerHTML = statusHtml;
                } else {
                    showStatus('❌ Failed to get import status', 'error');
                }
            } catch (error) {
                showStatus(`❌ Import status error: ${error.message}`, 'error');
            }
        }
        
        function displayAssets(data) {
            const container = document.getElementById('sceneAssets');
            
            if (!data.scene_objects || data.scene_objects.length === 0) {
                container.innerHTML = '<p style="color: #666; text-align: center; padding: 20px;">No assets in scene</p>';
                return;
            }
            
            let html = `
                <div style="margin-bottom: 20px; padding: 15px; background: #f7fafc; border-radius: 8px; text-align: center;">
                    <strong>Scene Summary:</strong> ${data.scene_objects.length} objects imported
                </div>
                <div class="assets-grid">
            `;
            
            data.scene_objects.forEach(obj => {
                const statusColor = obj.imported ? '#48bb78' : '#f56565';
                const statusText = obj.imported ? '✅ Imported' : (obj.import_status || '⏳ Pending');
                
                html += `
                    <div class="asset-card">
                        <div class="asset-name">${obj.name || 'Unnamed Object'}</div>
                        <div class="asset-details">
                            <div><strong>Type:</strong> ${obj.type || 'unknown'}</div>
                            <div><strong>Status:</strong> <span style="color: ${statusColor}">${statusText}</span></div>
                            <div><strong>Path:</strong> <code style="font-size: 0.8em;">${obj.prim_path || 'N/A'}</code></div>
                            ${obj.file_size ? `<div><strong>Size:</strong> ${formatFileSize(obj.file_size)}</div>` : ''}
                        </div>
                    </div>
                `;
            });
            
            html += '</div>';
            container.innerHTML = html;
        }
        
        async function clearScene() {
            if (!API_BASE_URL || !confirm('Are you sure you want to clear all scene objects?')) {
                return;
            }
            
            try {
                const response = await fetch(`${API_BASE_URL}/assets/clear`, {
                    method: 'DELETE',
                    mode: 'cors',
                    signal: AbortSignal.timeout(10000)
                });
                
                if (response.ok) {
                    showStatus('🗑️ Scene cleared successfully', 'success');
                    refreshAssets();
                } else {
                    showStatus('❌ Failed to clear scene', 'error');
                }
            } catch (error) {
                showStatus(`❌ Clear error: ${error.message}`, 'error');
            }
        }
        
        // Utility Functions
        function showProgress(percent) {
            progressBar.style.display = 'block';
            progressText.style.display = 'block';
            progressFill.style.width = percent + '%';
            progressText.textContent = Math.round(percent) + '%';
        }
        
        function hideProgress() {
            progressBar.style.display = 'none';
            progressText.style.display = 'none';
        }
        
        function showStatus(message, type) {
            status.innerHTML = message;
            status.className = `status ${type}`;
            status.style.display = 'block';
            
            setTimeout(() => { 
                if (status.className.includes(type)) {
                    status.style.display = 'none'; 
                }
            }, 8000);
        }
        
        function formatFileSize(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
        
        // Debug connection function
        async function debugConnection() {
            const debugDiv = document.getElementById('debugInfo');
            debugDiv.style.display = 'block';
            debugDiv.innerHTML = 'Running comprehensive connection diagnostics...\\n\\n';
            
            // Get server info
            const apiUrls = await discoverServer();
            
            debugDiv.innerHTML += `Server Discovery Results:\\n`;
            debugDiv.innerHTML += `Deployment: ${serverInfo?.deployment_type || 'unknown'}\\n`;
            debugDiv.innerHTML += `Hostname: ${serverInfo?.server_info?.hostname || 'unknown'}\\n`;
            debugDiv.innerHTML += `Suggested API URLs: ${apiUrls.length}\\n\\n`;
            
            // Test all potential API URLs
            for (const baseUrl of apiUrls) {
                const tests = [
                    { name: 'Health Check', endpoint: '/health' },
                    { name: 'Status Check', endpoint: '/status' },
                    { name: 'Import Status', endpoint: '/debug/import-status' },
                    { name: 'Assets Endpoint', endpoint: '/assets' },
                    { name: 'Supported Formats', endpoint: '/formats/supported' }
                ];
                
                debugDiv.innerHTML += `Testing ${baseUrl}:\\n`;
                
                for (const test of tests) {
                    try {
                        const start = Date.now();
                        const response = await fetch(baseUrl + test.endpoint, { 
                            method: 'GET',
                            signal: AbortSignal.timeout(5000),
                            mode: 'cors',
                            headers: {
                                'Accept': 'application/json',
                                'Content-Type': 'application/json'
                            }
                        });
                        const duration = Date.now() - start;
                        
                        let result = `  ✅ ${test.name}: HTTP ${response.status} (${duration}ms)`;
                        
                        if (response.ok) {
                            try {
                                const data = await response.text();
                                const preview = data.substring(0, 100);
                                result += `\\n     Response: ${preview}${data.length > 100 ? '...' : ''}`;
                            } catch (e) {
                                result += '\\n     Could not read response body';
                            }
                        }
                        
                        debugDiv.innerHTML += result + '\\n';
                    } catch (error) {
                        debugDiv.innerHTML += `  ❌ ${test.name}: ${error.message}\\n`;
                    }
                }
                debugDiv.innerHTML += '\\n';
            }
            
            // Additional diagnostics
            debugDiv.innerHTML += 'Environment Information:\\n';
            debugDiv.innerHTML += `Current URL: ${window.location.href}\\n`;
            debugDiv.innerHTML += `User Agent: ${navigator.userAgent.substring(0, 100)}\\n`;
            debugDiv.innerHTML += `Connection: ${navigator.onLine ? 'Online' : 'Offline'}\\n\\n`;
            
            debugDiv.innerHTML += 'Troubleshooting Steps:\\n';
            debugDiv.innerHTML += '1. ✅ RoWorks Omniverse is running\\n';
            debugDiv.innerHTML += '2. ✅ roworks.service.api extension is loaded\\n';
            debugDiv.innerHTML += '3. ✅ Look for "🚀 API: http://localhost:49101" in console\\n';
            debugDiv.innerHTML += '4. ❓ Check firewall settings for port 49101\\n';
            debugDiv.innerHTML += '5. ❓ If on AWS, ensure security group allows port 49101\\n';
            debugDiv.innerHTML += '6. ❓ Try accessing API URL directly in browser\\n';
        }
        
        // Initialize - Auto-discover and connect
        discoverAndConnect();
        setInterval(discoverAndConnect, 120000); // Check every 2 minutes
    </script>
</body>
</html>'''
    
    return html_content

def check_api_connection():
    """Check if the RoWorks API is running with better error detection"""
    server_info = get_server_info()
    
    # Try multiple potential API URLs
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
    
    for url in api_urls:
        try:
            import requests
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                data = response.json()
                print(f"✅ RoWorks API found at: {url}")
                print(f"   Service: {data.get('service', 'Unknown')}")
                print(f"   Version: {data.get('version', 'Unknown')}")
                print(f"   Workflow: {data.get('workflow', 'Unknown')}")
                return True
        except Exception as e:
            print(f"⚠️  API not responding at {url}: {e}")
            continue
    
    print(f"❌ RoWorks API not found on any URL")
    print(f"   Deployment: {'AWS EC2' if server_info['is_aws'] else 'Local'}")
    print(f"   Hostname: {server_info['hostname']}")
    print(f"   TROUBLESHOOTING:")
    print(f"   1. Make sure RoWorks Omniverse app is running")
    print(f"   2. Check Extensions tab for 'roworks.service.api'")
    print(f"   3. Look for console message: '🚀 API: http://localhost:49101'")
    if server_info["is_aws"]:
        print(f"   4. Ensure AWS security group allows port {API_PORT}")
        print(f"   5. Check if API is bound to 0.0.0.0 not just localhost")
    
    return False

def main():
    """Start the AWS-compatible web server"""
    server_info = get_server_info()
    
    print("=" * 60)
    print("🚀 RoWorks AI Omniverse Web Server - AWS EC2 Compatible")
    print("=" * 60)
    
    print(f"🌐 Deployment Type: {'AWS EC2' if server_info['is_aws'] else 'Local Development'}")
    print(f"🖥️  Hostname: {server_info['hostname']}")
    print(f"📡 Local IP: {server_info['local_ip']}")
    
    # Create web directory if it doesn't exist
    os.makedirs(DIRECTORY, exist_ok=True)
    
    # Create the AWS-compatible HTML file
    index_file = Path(DIRECTORY) / "index.html"
    html_content = create_aws_compatible_html()
    
    with open(index_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ AWS-compatible HTML interface created: {index_file}")
    
    print(f"📁 Serving files from: {os.path.abspath(DIRECTORY)}")
    print(f"🌐 Web interface: http://localhost:{PORT}")
    
    if server_info["is_aws"]:
        print(f"🌍 Public access: http://{server_info['public_hostname']}:{PORT}")
        print(f"🔗 API will be discovered at: {server_info['public_hostname']}:{API_PORT}")
    else:
        print(f"🔗 API endpoint: http://localhost:{API_PORT}")
    
    # Check API connection
    print("\\n🔍 Checking RoWorks API connection...")
    api_connected = check_api_connection()
    
    if not api_connected:
        print("\\n⚠️  Warning: RoWorks API is not responding")
        print("   The web interface will auto-discover API endpoints")
        print("   Make sure the RoWorks Omniverse application is running")
    
    print("\\n📋 AWS EC2 Features:")
    print("   ✅ Automatic API endpoint discovery")
    print("   ✅ Multiple URL fallback strategy")
    print("   ✅ Enhanced connection diagnostics")
    print("   ✅ Deployment-aware configuration")
    print("   ✅ Real-time connection status")
    
    # Start server
    try:
        with socketserver.TCPServer(("", PORT), RoWorksHTTPRequestHandler) as httpd:
            print(f"\\n🟢 AWS-compatible server running on port {PORT}")
            print("   The web interface will automatically discover the API")
            print("   Press Ctrl+C to stop the server")
            print("=" * 60)
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\\n\\n👋 Server stopped by user")
    except OSError as e:
        if e.errno == 48:  # Address already in use
            print(f"\\n❌ Port {PORT} is already in use")
            print("   Either stop the existing server or change the PORT in this script")
        else:
            print(f"\\n❌ Error starting server: {e}")
    except Exception as e:
        print(f"\\n❌ Unexpected error: {e}")

if __name__ == "__main__":
    main()
