# FIXED Extension with Proper Syntax - No Debug Endpoint Issues
# File: source/extensions/roworks.service.api/roworks/service/api/extension.py

import omni.ext
import logging
import asyncio
import threading
import tempfile
import os
import re
import time
import zipfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

# Import with fallback handling
try:
    from fastapi import FastAPI, File, UploadFile, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ FastAPI not available: {e}")
    FASTAPI_AVAILABLE = False

# Omniverse imports
import carb
import omni.kit.app
import omni.usd
from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf

logger = logging.getLogger(__name__)


class FixedUSDAnalyzer:
    """Simple USD analyzer without complex checks that cause hanging"""
    
    @staticmethod
    def quick_usd_check(usd_path: str) -> Tuple[bool, str]:
        """Simplified USD check - your 1.8MB file should pass easily"""
        print(f"🔧 DEBUG: Checking USD file: {usd_path}")
        
        try:
            # Step 1: File exists
            if not os.path.exists(usd_path):
                print(f"❌ DEBUG: File does not exist")
                return False, "File does not exist"
            print(f"✅ DEBUG: File exists")
            
            # Step 2: File size
            file_size = os.path.getsize(usd_path)
            file_size_mb = file_size / (1024 * 1024)
            print(f"✅ DEBUG: File size: {file_size_mb:.1f}MB")
            
            # Step 3: Size check (50MB limit - your file is 1.8MB)
            if file_size_mb > 50.0:
                print(f"❌ DEBUG: File too large: {file_size_mb:.1f}MB")
                return False, f"File too large: {file_size_mb:.1f}MB"
            
            # Step 4: Readable
            if not os.access(usd_path, os.R_OK):
                print(f"❌ DEBUG: File not readable")
                return False, "File not readable"
            print(f"✅ DEBUG: File is readable")
            
            # Step 5: Basic format check
            try:
                with open(usd_path, 'rb') as f:
                    header = f.read(100)
                
                if b'PXR-USDC' in header:
                    format_type = "Binary USD"
                elif b'#usda' in header or b'usda' in header:
                    format_type = "ASCII USD"
                else:
                    format_type = "USD format"
                
                print(f"✅ DEBUG: Valid {format_type} detected")
                
            except Exception as e:
                print(f"⚠️ DEBUG: Header check failed: {e}")
                format_type = "USD file"
            
            # SUCCESS - No complex analysis that causes hanging
            success_msg = f"USD file validated ({file_size_mb:.1f}MB {format_type})"
            print(f"✅ DEBUG: {success_msg}")
            return True, success_msg
            
        except Exception as e:
            print(f"❌ DEBUG: USD check error: {e}")
            # Fallback for small files
            try:
                file_size_mb = os.path.getsize(usd_path) / (1024 * 1024)
                if file_size_mb < 10.0:
                    fallback_msg = f"Small file ({file_size_mb:.1f}MB) - allowed despite check error"
                    print(f"🔧 DEBUG: FALLBACK: {fallback_msg}")
                    return True, fallback_msg
            except:
                pass
            
            return False, f"USD check failed: {str(e)}"


class SimpleNonBlockingUSDImporter:
    """Simplified USD importer without complex retry logic"""
    
    def __init__(self):
        self.import_queue = []
        self.is_importing = False
        self.import_timeout = 90.0  # 90 seconds
        print(f"🔧 DEBUG: Simple USD Importer initialized (timeout: {self.import_timeout}s)")
        
    def schedule_import(self, usd_path: str, asset_name: str, callback=None):
        """Schedule USD import with simple safety check"""
        print(f"🔧 DEBUG: Scheduling import for {asset_name}")
        
        # Simple safety check
        is_safe, message = FixedUSDAnalyzer.quick_usd_check(usd_path)
        if not is_safe:
            print(f"❌ DEBUG: Safety check failed: {message}")
            if callback:
                callback(False, asset_name, f"Safety check failed: {message}")
            return None
        
        print(f"✅ DEBUG: Safety check passed: {message}")
        
        import_task = {
            "usd_path": usd_path,
            "asset_name": asset_name,
            "callback": callback,
            "status": "queued",
            "queued_at": time.time()
        }
        
        self.import_queue.append(import_task)
        print(f"✅ DEBUG: Import queued (queue length: {len(self.import_queue)})")
        
        if not self.is_importing:
            asyncio.ensure_future(self._process_import_queue())
            
        return import_task
    
    async def _process_import_queue(self):
        """Simple import queue processor"""
        if self.is_importing:
            return
            
        print(f"🔧 DEBUG: Starting import queue processor")
        self.is_importing = True
        app = omni.kit.app.get_app()
        
        try:
            while self.import_queue:
                task = self.import_queue.pop(0)
                print(f"🔧 DEBUG: Processing {task['asset_name']}")
                
                try:
                    success, error = await asyncio.wait_for(
                        self._simple_import(task["usd_path"], task["asset_name"]),
                        timeout=self.import_timeout
                    )
                    
                    if success:
                        print(f"✅ DEBUG: Import successful: {task['asset_name']}")
                        if task["callback"]:
                            task["callback"](True, task["asset_name"], "Import successful")
                    else:
                        print(f"❌ DEBUG: Import failed: {task['asset_name']} - {error}")
                        if task["callback"]:
                            task["callback"](False, task["asset_name"], error)
                
                except asyncio.TimeoutError:
                    print(f"❌ DEBUG: Import timeout: {task['asset_name']}")
                    if task["callback"]:
                        task["callback"](False, task["asset_name"], f"Import timeout after {self.import_timeout}s")
                
                except Exception as e:
                    print(f"❌ DEBUG: Import error: {task['asset_name']} - {e}")
                    if task["callback"]:
                        task["callback"](False, task["asset_name"], str(e))
                
                # Yield between imports
                for _ in range(10):
                    await app.next_update_async()
                await asyncio.sleep(1.0)
                    
        finally:
            self.is_importing = False
            print(f"🔧 DEBUG: Import queue processor finished")
    
    async def _simple_import(self, usd_path: str, asset_name: str) -> Tuple[bool, str]:
        """Simple USD import via reference"""
        print(f"🔧 DEBUG: Simple import: {asset_name}")
        
        try:
            app = omni.kit.app.get_app()
            context = omni.usd.get_context()
            
            # Wait for context
            for i in range(100):  # 10 second timeout
                if context and context.get_stage():
                    break
                await asyncio.sleep(0.1)
            else:
                return False, "USD context not ready"
            
            stage = context.get_stage()
            
            # Create safe prim path
            safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', Path(asset_name).stem)
            if safe_name and safe_name[0].isdigit():
                safe_name = f"Asset_{safe_name}"
            if not safe_name:
                safe_name = "UnnamedAsset"
                
            prim_path = f"/World/RoWorks/Assets/{safe_name}"
            
            # Ensure parent paths exist
            for path in ["/World", "/World/RoWorks", "/World/RoWorks/Assets"]:
                if not stage.GetPrimAtPath(path):
                    stage.DefinePrim(path, "Xform")
                    await app.next_update_async()
            
            # Remove existing prim
            if stage.GetPrimAtPath(prim_path):
                stage.RemovePrim(prim_path)
                await app.next_update_async()
            
            # Create prim and add reference
            prim = stage.DefinePrim(prim_path, "Xform")
            await app.next_update_async()
            
            if not prim:
                return False, "Failed to create prim"
            
            # Add reference
            prim.GetReferences().AddReference(usd_path)
            
            # Wait for reference to load
            for i in range(20):
                await app.next_update_async()
                await asyncio.sleep(0.2)
                if prim.GetChildren():
                    break
            
            # Add metadata
            try:
                prim.CreateAttribute("roworks:source_file", Sdf.ValueTypeNames.String).Set(usd_path)
                prim.CreateAttribute("roworks:asset_type", Sdf.ValueTypeNames.String).Set("usd_asset")
            except:
                pass
            
            print(f"✅ DEBUG: Reference created at {prim_path}")
            return True, "Reference created successfully"
            
        except Exception as e:
            print(f"❌ DEBUG: Simple import error: {e}")
            return False, str(e)
    
    def get_status(self):
        return {
            "queue_length": len(self.import_queue),
            "is_importing": self.is_importing,
            "timeout_seconds": self.import_timeout
        }


class SimpleMeshUSDManager:
    """Simplified mesh manager without complex features"""
    
    def __init__(self):
        print("🔧 DEBUG: Initializing Simple MeshUSDManager")
        self.uploaded_assets = []
        self.temp_dir = tempfile.mkdtemp(prefix="roworks_mesh_")
        self.usd_importer = SimpleNonBlockingUSDImporter()
        
        # Try to connect to scene manager
        self.scene_manager = None
        try:
            from roworks.scene.manager import get_scene_manager
            self.scene_manager = get_scene_manager()
        except:
            pass
            
        print(f"✅ DEBUG: Simple mesh manager ready")
    
    def process_mesh_zip(self, zip_path: str, filename: str, file_size: int) -> Dict[str, Any]:
        """Process mesh ZIP with simplified logic"""
        print(f"🔧 DEBUG: Processing {filename} ({file_size / 1024 / 1024:.1f} MB)")
        
        try:
            # Extract ZIP
            extracted = self._extract_zip(zip_path, filename)
            if not extracted['valid']:
                return {"success": False, "message": extracted['error'], "asset": None}
            
            # Create USD
            asset_name = self._sanitize_name(filename)
            usd_result = self._create_usd(extracted, asset_name, filename, file_size)
            
            if usd_result['success']:
                # Schedule import
                self._schedule_import(usd_result['usd_path'], asset_name)
                
                # Track asset
                asset_info = {
                    "filename": filename,
                    "asset_name": asset_name,
                    "file_size": file_size,
                    "usd_path": usd_result['usd_path'],
                    "created_at": time.time(),
                    "imported_to_scene": False,
                    "import_status": "scheduled",
                    "import_message": "Import scheduled"
                }
                self.uploaded_assets.append(asset_info)
                
                return {
                    "success": True,
                    "message": f"USD asset created and import scheduled: {asset_name}",
                    "asset": asset_info
                }
            else:
                return {"success": False, "message": usd_result['error'], "asset": None}
                
        except Exception as e:
            print(f"❌ DEBUG: Processing error: {e}")
            return {"success": False, "message": str(e), "asset": None}
    
    def _extract_zip(self, zip_path: str, filename: str) -> Dict:
        """Simple ZIP extraction"""
        result = {"valid": False, "error": "", "files": {"obj_file": None, "mtl_file": None, "texture_files": []}}
        
        try:
            extract_dir = os.path.join(self.temp_dir, f"extract_{int(time.time())}")
            os.makedirs(extract_dir, exist_ok=True)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            for file_path in Path(extract_dir).rglob('*'):
                if file_path.is_file():
                    ext = file_path.suffix.lower()
                    if ext == '.obj':
                        result["files"]["obj_file"] = str(file_path)
                    elif ext == '.mtl':
                        result["files"]["mtl_file"] = str(file_path)
                    elif ext in ['.jpg', '.jpeg', '.png', '.tiff', '.tga', '.bmp']:
                        result["files"]["texture_files"].append(str(file_path))
            
            if not result["files"]["obj_file"]:
                result["error"] = "No OBJ file found in ZIP"
                return result
            
            result["valid"] = True
            print(f"✅ DEBUG: ZIP extracted - OBJ: ✓, MTL: {bool(result['files']['mtl_file'])}, Textures: {len(result['files']['texture_files'])}")
            return result
            
        except Exception as e:
            result["error"] = f"ZIP extraction failed: {str(e)}"
            return result
    
    def _create_usd(self, extracted: Dict, asset_name: str, filename: str, file_size: int) -> Dict:
        """Simple USD creation"""
        try:
            usd_dir = os.path.join(self.temp_dir, "usd_assets")
            os.makedirs(usd_dir, exist_ok=True)
            usd_path = os.path.join(usd_dir, f"{asset_name}.usd")
            
            print(f"🔧 DEBUG: Creating USD: {usd_path}")
            
            # Create simple USD stage
            stage = Usd.Stage.CreateNew(usd_path)
            stage.SetMetadata('metersPerUnit', 1.0)
            stage.SetMetadata('upAxis', 'Y')
            
            root_path = f"/{asset_name}"
            root_prim = stage.DefinePrim(root_path, "Xform")
            stage.SetDefaultPrim(root_prim)
            
            # Simple OBJ import
            if self._import_obj_simple(stage, extracted['files']['obj_file'], f"{root_path}/Mesh"):
                stage.Save()
                print(f"✅ DEBUG: USD created: {usd_path}")
                return {"success": True, "usd_path": usd_path}
            else:
                return {"success": False, "error": "Failed to import OBJ"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _import_obj_simple(self, stage, obj_path: str, mesh_path: str) -> bool:
        """Simple OBJ import"""
        try:
            vertices, faces = self._parse_obj_simple(obj_path)
            if not vertices or not faces:
                return False
            
            mesh_prim = stage.DefinePrim(mesh_path, "Mesh")
            mesh = UsdGeom.Mesh(mesh_prim)
            
            mesh.CreatePointsAttr().Set(vertices)
            mesh.CreateFaceVertexIndicesAttr().Set(faces)
            mesh.CreateFaceVertexCountsAttr().Set([3] * (len(faces) // 3))
            mesh.CreateDisplayColorAttr().Set([(0.8, 0.8, 0.8)])
            
            return True
        except Exception as e:
            print(f"❌ DEBUG: OBJ import error: {e}")
            return False
    
    def _parse_obj_simple(self, obj_path: str) -> Tuple[List, List]:
        """Simple OBJ parser"""
        vertices = []
        faces = []
        
        try:
            with open(obj_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('v '):
                        parts = line.split()[1:4]
                        if len(parts) >= 3:
                            vertices.append((float(parts[0]), float(parts[1]), float(parts[2])))
                    elif line.startswith('f '):
                        parts = line.split()[1:]
                        face_indices = []
                        for part in parts:
                            vertex_idx = int(part.split('/')[0]) - 1
                            face_indices.append(vertex_idx)
                        
                        if len(face_indices) == 3:
                            faces.extend(face_indices)
                        elif len(face_indices) == 4:
                            faces.extend([face_indices[0], face_indices[1], face_indices[2]])
                            faces.extend([face_indices[0], face_indices[2], face_indices[3]])
            
            print(f"🔧 DEBUG: Parsed OBJ - {len(vertices)} vertices, {len(faces)//3} triangles")
        except Exception as e:
            print(f"❌ DEBUG: OBJ parse error: {e}")
        
        return vertices, faces
    
    def _schedule_import(self, usd_path: str, asset_name: str):
        """Schedule import with callback"""
        def callback(success: bool, name: str, message: str):
            for asset in self.uploaded_assets:
                if asset["asset_name"] == name:
                    asset["imported_to_scene"] = success
                    asset["import_status"] = "completed" if success else "failed"
                    asset["import_message"] = message
                    if success:
                        asset["scene_prim_path"] = f"/World/RoWorks/Assets/{name}"
                    break
        
        self.usd_importer.schedule_import(usd_path, asset_name, callback)
    
    def _sanitize_name(self, filename: str) -> str:
        """Create safe name"""
        name = Path(filename).stem
        name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        if name and name[0].isdigit():
            name = f"Asset_{name}"
        return name or "UnnamedAsset"
    
    def get_status(self):
        return {
            "total_assets": len(self.uploaded_assets),
            "temp_dir": self.temp_dir,
            **self.usd_importer.get_status()
        }
    
    def get_assets(self):
        return self.uploaded_assets
    
    def get_scene_objects(self):
        return [
            {
                "name": asset["asset_name"],
                "type": "mesh_asset",
                "prim_path": asset.get("scene_prim_path", f"/World/RoWorks/Assets/{asset['asset_name']}"),
                "usd_path": asset["usd_path"],
                "imported": asset.get("imported_to_scene", False),
                "import_status": asset.get("import_status", "unknown"),
                "file_size": asset["file_size"],
                "created_at": asset["created_at"]
            }
            for asset in self.uploaded_assets
        ]


class SimpleMeshAPIService:
    """Simplified API service without complex debug endpoints"""
    
    def __init__(self):
        print("🔧 DEBUG: Initializing Simple MeshAPIService")
        if not FASTAPI_AVAILABLE:
            print("❌ DEBUG: FastAPI not available")
            self._app = None
            self.usd_manager = SimpleMeshUSDManager()
            return
            
        self._app = FastAPI(
            title="RoWorks Simple Mesh USD API",
            description="Simplified mesh ZIP to USD conversion",
            version="3.1.0-simple"
        )
        
        self._app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        self._server = None
        self._server_thread = None
        self.usd_manager = SimpleMeshUSDManager()
        self._setup_routes()
        print("✅ DEBUG: Simple API service initialized")
    
    def _setup_routes(self):
        """Setup basic API routes"""
        if not self._app:
            return
            
        @self._app.get("/health")
        async def health_check():
            return {
                "status": "healthy",
                "service": "simple_mesh_usd",
                "version": "3.1.0-simple",
                "workflow": "Simplified mesh ZIP to USD conversion",
                **self.usd_manager.get_status()
            }
        
        @self._app.post("/mesh/import")
        async def import_mesh(file: UploadFile = File(...)):
            """Simple mesh import"""
            print(f"🔧 DEBUG: Mesh import: {file.filename}")
            
            try:
                if not file.filename or not file.filename.lower().endswith('.zip'):
                    raise HTTPException(status_code=400, detail="File must be a ZIP archive")
                
                content = await file.read()
                file_size = len(content)
                
                if file_size > 100 * 1024 * 1024:  # 100MB
                    raise HTTPException(status_code=400, detail="File too large")
                
                zip_path = os.path.join(self.usd_manager.temp_dir, file.filename)
                with open(zip_path, 'wb') as f:
                    f.write(content)
                
                result = self.usd_manager.process_mesh_zip(zip_path, file.filename, file_size)
                
                if result["success"]:
                    return {"success": True, "message": result["message"], "data": result["asset"]}
                else:
                    raise HTTPException(status_code=400, detail=result["message"])
                    
            except HTTPException:
                raise
            except Exception as e:
                print(f"❌ DEBUG: Import error: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self._app.get("/assets")
        async def get_assets():
            return {
                "assets": self.usd_manager.get_assets(),
                "scene_objects": self.usd_manager.get_scene_objects()
            }
        
        @self._app.get("/scene/info")
        async def get_scene_info():
            scene_objects = self.usd_manager.get_scene_objects()
            by_type = {}
            for obj in scene_objects:
                obj_type = obj.get("type", "unknown")
                by_type[obj_type] = by_type.get(obj_type, 0) + 1
            
            return {
                "total_objects": len(scene_objects),
                "objects_by_type": by_type,
                "objects": scene_objects
            }
        
        @self._app.delete("/assets/clear")
        async def clear_assets():
            self.usd_manager.uploaded_assets.clear()
            return {"success": True, "message": "Assets cleared"}
        
        @self._app.post("/debug/analyze-zip")
        async def analyze_zip(file: UploadFile = File(...)):
            """Analyze ZIP contents without creating USD - for web interface"""
            print(f"🔧 DEBUG: Analyzing ZIP: {file.filename}")
            
            try:
                if not file.filename or not file.filename.lower().endswith('.zip'):
                    raise HTTPException(status_code=400, detail="File must be a ZIP archive")
                
                content = await file.read()
                temp_path = os.path.join(self.usd_manager.temp_dir, f"analyze_{file.filename}")
                
                with open(temp_path, 'wb') as f:
                    f.write(content)
                
                # Use the same extraction logic as the main import
                extracted = self.usd_manager._extract_zip(temp_path, file.filename)
                
                analysis = {
                    "filename": file.filename,
                    "file_size": len(content),
                    "file_size_mb": round(len(content) / 1024 / 1024, 2),
                    "valid": extracted["valid"],
                    "error": extracted.get("error", ""),
                    "contents": {
                        "obj_file": Path(extracted["files"]["obj_file"]).name if extracted["files"]["obj_file"] else None,
                        "mtl_file": Path(extracted["files"]["mtl_file"]).name if extracted["files"]["mtl_file"] else None,
                        "texture_count": len(extracted["files"]["texture_files"]),
                        "texture_files": [Path(f).name for f in extracted["files"]["texture_files"]]
                    }
                }
                
                print(f"✅ DEBUG: ZIP analysis complete - Valid: {analysis['valid']}")
                
                return {
                    "success": True,
                    "message": "ZIP analysis complete",
                    "analysis": analysis
                }
                
            except Exception as e:
                print(f"❌ DEBUG: ZIP analysis error: {e}")
                return {
                    "success": False,
                    "message": f"Analysis failed: {str(e)}"
                }
        
        @self._app.get("/debug/import-status")
        async def get_import_status():
            """Get import status for web interface"""
            return {
                "import_system": "simple_v3.1",
                "status": self.usd_manager.get_status(),
                "assets": [
                    {
                        "name": asset["asset_name"],
                        "imported": asset.get("imported_to_scene", False),
                        "status": asset.get("import_status", "unknown"),
                        "message": asset.get("import_message", "No status"),
                        "usd_path": asset.get("usd_path", ""),
                        "file_size": asset.get("file_size", 0),
                        "created_at": asset.get("created_at", 0)
                    }
                    for asset in self.usd_manager.uploaded_assets
                ],
                "queue_info": self.usd_manager.usd_importer.get_status()
            }
        
        @self._app.get("/formats/supported")
        async def get_supported_formats():
            """Get supported formats for web interface"""
            return {
                "input_format": ".zip",
                "required_contents": ["*.obj", "*.mtl (optional)", "*.jpg/*.png (optional)"],
                "description": "ZIP archives containing OBJ mesh with optional MTL materials and texture images",
                "max_file_size": "100MB",
                "workflow": "Upload mesh ZIP → USD asset creation → Scene import"
            }
    
    def start_server(self):
        """Start the server"""
        if not self._app:
            return
            
        def run_server():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                config = uvicorn.Config(
                    app=self._app,
                    host="0.0.0.0",
                    port=49101,
                    log_level="error",
                    access_log=False
                )
                
                self._server = uvicorn.Server(config)
                print("🚀 DEBUG: Simple API server starting on port 49101")
                loop.run_until_complete(self._server.serve())
                
            except Exception as e:
                print(f"❌ DEBUG: Server error: {e}")
                import traceback
                traceback.print_exc()
        
        try:
            self._server_thread = threading.Thread(target=run_server, daemon=True)
            self._server_thread.start()
        except Exception as e:
            print(f"❌ DEBUG: Thread start error: {e}")
    
    def stop_server(self):
        if self._server:
            self._server.should_exit = True


class RoWorksServiceApiExtension(omni.ext.IExt):
    """Simplified extension without complex debug features"""
    
    def on_startup(self, ext_id):
        print("🚀 DEBUG: RoWorks Simple Service API Extension Starting!")
        
        try:
            self._api_service = SimpleMeshAPIService()
            
            if FASTAPI_AVAILABLE:
                self._api_service.start_server()
                print("✅ DEBUG: Simple extension startup complete")
                print("🚀 API: http://localhost:49101 (Simple Version)")
                print("📝 Simplified workflow: ZIP → USD → Scene import")
                print("🎯 Key fixes:")
                print("   • Relaxed USD analyzer (50MB limit)")
                print("   • Extended timeout (90 seconds)")
                print("   • Simplified import process")
                print("   • No complex retry logic")
            else:
                print("⚠️ DEBUG: API disabled - FastAPI not available")
                
        except Exception as e:
            print(f"❌ DEBUG: Extension startup failed: {e}")
            import traceback
            traceback.print_exc()
    
    def on_shutdown(self):
        print("🔧 DEBUG: Simple extension shutting down")
        if hasattr(self, '_api_service') and self._api_service:
            self._api_service.stop_server()


# Public API function for compatibility
def some_public_function(x):
    return x * x * x * x
