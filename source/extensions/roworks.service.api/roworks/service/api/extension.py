import omni.ext
import logging
import asyncio
import threading
import tempfile
import os
import re
import time
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import Dict, Any, Optional

# Omniverse imports
import carb
import omni.kit.app
import omni.usd
from pxr import Usd, UsdGeom, Sdf

logger = logging.getLogger(__name__)

class BatchUSDManager:
    """Collects files and creates USD scene when ready"""
    
    def __init__(self):
        print("🔧 DEBUG: Initializing BatchUSDManager")
        self.uploaded_files = {
            "mesh": None,
            "pointcloud": None,
            "robot": None
        }
        self.scene_objects = []
        self.usd_scene_created = False
        print("🔧 DEBUG: Batch USD manager initialized")
    
    def add_uploaded_file(self, file_type: str, filename: str, file_path: str, file_size: int) -> Dict[str, Any]:
        """Add an uploaded file and check if we're ready to create USD"""
        print(f"🔧 DEBUG: Adding {file_type} file: {filename}")
        
        self.uploaded_files[file_type] = {
            "filename": filename,
            "file_path": file_path,
            "file_size": file_size,
            "uploaded_at": time.time()
        }
        
        # Check if we have both mesh and pointcloud
        has_mesh = self.uploaded_files["mesh"] is not None
        has_pointcloud = self.uploaded_files["pointcloud"] is not None
        
        print(f"🔧 DEBUG: Files status - Mesh: {has_mesh}, PointCloud: {has_pointcloud}")
        
        result = {
            "file_added": True,
            "files_ready": has_mesh and has_pointcloud,
            "uploaded_files": {k: v["filename"] if v else None for k, v in self.uploaded_files.items()}
        }
        
        if has_mesh and has_pointcloud and not self.usd_scene_created:
            print("🎬 DEBUG: Both files ready! Triggering USD scene creation...")
            self._schedule_usd_creation()
            result["usd_creation_triggered"] = True
        
        return result
    
    def _schedule_usd_creation(self):
        """Schedule USD creation on the main thread"""
        print("🔧 DEBUG: Scheduling USD creation on main thread")
        
        # Use Omniverse's main thread scheduler
        async def create_usd_scene():
            print("🔧 DEBUG: [Main Thread] Starting USD scene creation")
            try:
                await self._create_complete_usd_scene()
            except Exception as e:
                print(f"❌ DEBUG: [Main Thread] USD creation failed: {e}")
        
        # Schedule on main thread
        app = omni.kit.app.get_app()
        asyncio.ensure_future(create_usd_scene())
    
    async def _create_complete_usd_scene(self):
        """Create the complete USD scene with mesh and pointcloud"""
        print("🎬 DEBUG: Creating complete USD scene")
        
        try:
            # Wait a frame to ensure we're on main thread
            app = omni.kit.app.get_app()
            await app.next_update_async()
            
            # Get USD context and stage
            context = omni.usd.get_context()
            stage = context.get_stage()
            
            if not stage:
                print("❌ DEBUG: No USD stage available")
                return False
            
            print("✅ DEBUG: USD stage available, creating scene...")
            
            # Create base hierarchy
            self._create_base_hierarchy(stage)
            
            # Create mesh object
            if self.uploaded_files["mesh"]:
                await self._create_mesh_object(stage, self.uploaded_files["mesh"])
                await app.next_update_async()  # Let UI update
            
            # Create pointcloud object
            if self.uploaded_files["pointcloud"]:
                await self._create_pointcloud_object(stage, self.uploaded_files["pointcloud"])
                await app.next_update_async()  # Let UI update
            
            # Create robot if available
            if self.uploaded_files["robot"]:
                await self._create_robot_object(stage, self.uploaded_files["robot"])
                await app.next_update_async()  # Let UI update
            
            self.usd_scene_created = True
            print("🎉 DEBUG: Complete USD scene created successfully!")
            
            return True
            
        except Exception as e:
            print(f"❌ DEBUG: Error creating USD scene: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _create_base_hierarchy(self, stage):
        """Create the RoWorks folder structure"""
        print("🔧 DEBUG: Creating base USD hierarchy")
        
        # Create /World/RoWorks if it doesn't exist
        if not stage.GetPrimAtPath("/World/RoWorks"):
            roworks_prim = stage.DefinePrim("/World/RoWorks", "Xform")
            print("✅ DEBUG: Created /World/RoWorks")
        
        # Create subfolders
        folders = ["Meshes", "PointClouds", "Robots"]
        for folder in folders:
            folder_path = f"/World/RoWorks/{folder}"
            if not stage.GetPrimAtPath(folder_path):
                stage.DefinePrim(folder_path, "Xform")
                print(f"✅ DEBUG: Created {folder_path}")
    
    async def _create_mesh_object(self, stage, mesh_info):
        """Create mesh object in USD"""
        print(f"🔧 DEBUG: Creating mesh object: {mesh_info['filename']}")
        
        try:
            safe_name = self._sanitize_name(mesh_info['filename'])
            prim_path = f"/World/RoWorks/Meshes/{safe_name}"
            
            # Create main prim
            mesh_prim = stage.DefinePrim(prim_path, "Xform")
            
            # Add metadata
            mesh_prim.CreateAttribute("roworks:source_file", Sdf.ValueTypeNames.String).Set(mesh_info['filename'])
            mesh_prim.CreateAttribute("roworks:file_type", Sdf.ValueTypeNames.String).Set("mesh")
            mesh_prim.CreateAttribute("roworks:file_size", Sdf.ValueTypeNames.Int).Set(mesh_info['file_size'])
            
            # Create cube geometry as placeholder
            cube_path = f"{prim_path}/geometry"
            cube_prim = stage.DefinePrim(cube_path, "Cube")
            cube_geom = UsdGeom.Cube(cube_prim)
            
            # Set properties
            cube_geom.CreateSizeAttr().Set(2.0)  # Make it bigger
            cube_geom.CreateDisplayColorAttr().Set([(0.8, 0.2, 0.2)])  # Red for mesh
            
            # Position it
            xform = UsdGeom.Xformable(mesh_prim)
            xform.AddTranslateOp().Set((-3, 0, 0))  # Left side
            
            # Track object
            obj_info = {
                "name": mesh_info['filename'],
                "type": "mesh",
                "prim_path": prim_path,
                "created": True,
                "file_size": mesh_info['file_size']
            }
            self.scene_objects.append(obj_info)
            
            print(f"✅ DEBUG: Mesh object created at {prim_path}")
            
        except Exception as e:
            print(f"❌ DEBUG: Error creating mesh object: {e}")
    
    async def _create_pointcloud_object(self, stage, pc_info):
        """Create pointcloud object in USD"""
        print(f"🔧 DEBUG: Creating pointcloud object: {pc_info['filename']}")
        
        try:
            safe_name = self._sanitize_name(pc_info['filename'])
            prim_path = f"/World/RoWorks/PointClouds/{safe_name}"
            
            # Create main prim
            pc_prim = stage.DefinePrim(prim_path, "Xform")
            
            # Add metadata
            pc_prim.CreateAttribute("roworks:source_file", Sdf.ValueTypeNames.String).Set(pc_info['filename'])
            pc_prim.CreateAttribute("roworks:file_type", Sdf.ValueTypeNames.String).Set("pointcloud")
            pc_prim.CreateAttribute("roworks:file_size", Sdf.ValueTypeNames.Int).Set(pc_info['file_size'])
            
            # Position it
            xform = UsdGeom.Xformable(pc_prim)
            xform.AddTranslateOp().Set((3, 0, 0))  # Right side
            
            # Load point data
            points = self._load_pointcloud_data(pc_info['file_path'])
            
            # Create points geometry
            points_path = f"{prim_path}/points"
            points_prim = stage.DefinePrim(points_path, "Points")
            points_geom = UsdGeom.Points(points_prim)
            
            # Set point data
            points_geom.CreatePointsAttr().Set(points)
            points_geom.CreateDisplayColorAttr().Set([(0.2, 0.6, 1.0)])  # Blue for pointcloud
            points_geom.CreateWidthsAttr().Set([2.0] * len(points))
            
            # Track object
            obj_info = {
                "name": pc_info['filename'],
                "type": "pointcloud",
                "prim_path": prim_path,
                "created": True,
                "file_size": pc_info['file_size'],
                "point_count": len(points)
            }
            self.scene_objects.append(obj_info)
            
            print(f"✅ DEBUG: Pointcloud object created at {prim_path} with {len(points)} points")
            
        except Exception as e:
            print(f"❌ DEBUG: Error creating pointcloud object: {e}")
    
    async def _create_robot_object(self, stage, robot_info):
        """Create robot object in USD"""
        print(f"🔧 DEBUG: Creating robot object: {robot_info['filename']}")
        
        try:
            safe_name = self._sanitize_name(robot_info['filename'])
            prim_path = f"/World/RoWorks/Robots/{safe_name}"
            
            # Create main prim
            robot_prim = stage.DefinePrim(prim_path, "Xform")
            
            # Add metadata
            robot_prim.CreateAttribute("roworks:source_file", Sdf.ValueTypeNames.String).Set(robot_info['filename'])
            robot_prim.CreateAttribute("roworks:file_type", Sdf.ValueTypeNames.String).Set("robot")
            robot_prim.CreateAttribute("roworks:file_size", Sdf.ValueTypeNames.Int).Set(robot_info['file_size'])
            
            # Position it
            xform = UsdGeom.Xformable(robot_prim)
            xform.AddTranslateOp().Set((0, 0, 0))  # Center
            
            # Create robot base
            base_path = f"{prim_path}/base"
            base_prim = stage.DefinePrim(base_path, "Cube")
            base_geom = UsdGeom.Cube(base_prim)
            base_geom.CreateSizeAttr().Set(0.8)
            base_geom.CreateDisplayColorAttr().Set([(0.2, 0.2, 0.8)])  # Blue base
            
            # Create robot arm
            arm_path = f"{prim_path}/arm"
            arm_prim = stage.DefinePrim(arm_path, "Cylinder")
            arm_xform = UsdGeom.Xformable(arm_prim)
            arm_xform.AddTranslateOp().Set((0, 0, 1.0))
            
            arm_geom = UsdGeom.Cylinder(arm_prim)
            arm_geom.CreateRadiusAttr().Set(0.1)
            arm_geom.CreateHeightAttr().Set(1.5)
            arm_geom.CreateDisplayColorAttr().Set([(0.8, 0.6, 0.2)])  # Orange arm
            
            # Track object
            obj_info = {
                "name": robot_info['filename'],
                "type": "robot",
                "prim_path": prim_path,
                "created": True,
                "file_size": robot_info['file_size']
            }
            self.scene_objects.append(obj_info)
            
            print(f"✅ DEBUG: Robot object created at {prim_path}")
            
        except Exception as e:
            print(f"❌ DEBUG: Error creating robot object: {e}")
    
    def _load_pointcloud_data(self, file_path: str) -> list:
        """Load point cloud data from file"""
        points = []
        
        try:
            file_ext = Path(file_path).suffix.lower()
            
            if file_ext == '.xyz':
                with open(file_path, 'r') as f:
                    for line_num, line in enumerate(f):
                        if line_num > 5000:  # Limit for performance
                            break
                        parts = line.strip().split()
                        if len(parts) >= 3:
                            try:
                                x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                                points.append((x, y, z))
                            except ValueError:
                                continue
        except Exception as e:
            print(f"⚠️ DEBUG: Could not read point cloud file: {e}")
        
        # Fallback to sample points
        if not points:
            points = [
                (0, 0, 0), (0.5, 0, 0), (0, 0.5, 0), (0, 0, 0.5),
                (0.5, 0.5, 0), (0.5, 0, 0.5), (0, 0.5, 0.5), (0.5, 0.5, 0.5),
                (0.25, 0.25, 0.25), (-0.25, 0.25, 0.25), (0.25, -0.25, 0.25)
            ]
        
        print(f"🔧 DEBUG: Loaded {len(points)} points")
        return points
    
    def _sanitize_name(self, filename: str) -> str:
        """Create safe USD prim name"""
        name = Path(filename).stem
        name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        if name and name[0].isdigit():
            name = f"Object_{name}"
        if not name:
            name = "UnnamedObject"
        return name
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status"""
        return {
            "uploaded_files": {k: v["filename"] if v else None for k, v in self.uploaded_files.items()},
            "usd_scene_created": self.usd_scene_created,
            "scene_objects": len(self.scene_objects),
            "ready_for_usd": self.uploaded_files["mesh"] is not None and self.uploaded_files["pointcloud"] is not None
        }
    
    def get_scene_stats(self) -> Dict[str, Any]:
        """Get scene statistics"""
        by_type = {}
        for obj in self.scene_objects:
            obj_type = obj["type"]
            by_type[obj_type] = by_type.get(obj_type, 0) + 1
        
        return {
            "total_objects": len(self.scene_objects),
            "objects_by_type": by_type,
            "objects": self.scene_objects,
            "status": self.get_status()
        }


class BatchAPIService:
    """API service for batch USD creation"""
    
    def __init__(self):
        print("🔧 DEBUG: Initializing BatchAPIService")
        self._app = FastAPI(
            title="RoWorks Batch USD API",
            description="Collects files and creates USD scene when ready",
            version="1.0.0"
        )
        
        # Enable CORS
        self._app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        self._server = None
        self._server_thread = None
        self._temp_dir = tempfile.mkdtemp(prefix="roworks_batch_")
        
        self.usd_manager = BatchUSDManager()
        self._setup_routes()
        print("🔧 DEBUG: Batch API Service initialized")
    
    def _setup_routes(self):
        """Setup API routes"""
        
        @self._app.get("/health")
        async def health_check():
            return {
                "status": "healthy",
                "api": "batch_usd_creation",
                "temp_dir": self._temp_dir,
                **self.usd_manager.get_status()
            }
        
        @self._app.get("/status")
        async def get_status():
            return self.usd_manager.get_status()
        
        @self._app.get("/scene/info")
        async def get_scene_info():
            return self.usd_manager.get_scene_stats()
        
        @self._app.post("/mesh/import")
        async def import_mesh(file: UploadFile = File(...)):
            return await self._handle_file_upload(file, "mesh")
        
        @self._app.post("/pointcloud/import")
        async def import_pointcloud(file: UploadFile = File(...)):
            return await self._handle_file_upload(file, "pointcloud")
        
        @self._app.post("/robot/import")
        async def import_robot(file: UploadFile = File(...)):
            return await self._handle_file_upload(file, "robot")
        
        @self._app.delete("/scene/clear")
        async def clear_scene():
            self.usd_manager.scene_objects.clear()
            self.usd_manager.uploaded_files = {"mesh": None, "pointcloud": None, "robot": None}
            self.usd_manager.usd_scene_created = False
            return {"success": True, "message": "Scene and uploads cleared"}
    
    async def _handle_file_upload(self, file: UploadFile, file_type: str):
        """Handle file upload and batch processing"""
        print(f"🔧 DEBUG: Handling {file_type} upload: {file.filename}")
        start_time = time.time()
        
        try:
            # Validate file
            if not file.filename:
                raise HTTPException(status_code=400, detail="No file provided")
            
            # Read content
            content = await file.read()
            file_size = len(content)
            print(f"🔧 DEBUG: File size: {file_size} bytes")
            
            # Save file
            file_path = os.path.join(self._temp_dir, file.filename)
            with open(file_path, 'wb') as f:
                f.write(content)
            
            # Add to batch manager
            result = self.usd_manager.add_uploaded_file(file_type, file.filename, file_path, file_size)
            
            elapsed_time = time.time() - start_time
            print(f"🔧 DEBUG: Upload processed in {elapsed_time:.2f}s")
            
            return {
                "success": True,
                "message": f"{file_type.capitalize()} '{file.filename}' uploaded successfully",
                "data": {
                    "name": file.filename,
                    "object_type": file_type,
                    "file_size": file_size,
                    "processing_time": elapsed_time
                },
                "batch_status": result
            }
                
        except Exception as e:
            elapsed_time = time.time() - start_time
            print(f"❌ DEBUG: Upload error after {elapsed_time:.2f}s: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    def start_server(self):
        """Start the API server"""
        def run_server():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                config = uvicorn.Config(
                    app=self._app,
                    host="0.0.0.0",
                    port=49101,
                    log_level="warning",
                    access_log=False
                )
                
                self._server = uvicorn.Server(config)
                print("🚀 DEBUG: Batch USD API server starting on port 49101")
                
                loop.run_until_complete(self._server.serve())
                
            except Exception as e:
                print(f"❌ DEBUG: Server error: {e}")
        
        self._server_thread = threading.Thread(target=run_server, daemon=True)
        self._server_thread.start()
    
    def stop_server(self):
        if self._server:
            self._server.should_exit = True


class RoWorksServiceApiExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        print("🚀 DEBUG: RoWorks Batch USD API Extension Starting!")
        
        try:
            self._api_service = BatchAPIService()
            self._api_service.start_server()
            
            print("✅ DEBUG: Batch USD extension startup complete")
            print(f"🚀 API: http://localhost:49101 (Batch USD Creation)")
            print("📝 Upload mesh + pointcloud files to trigger USD scene creation")
            print("🎬 USD scene will be created when both files are ready")
            
        except Exception as e:
            print(f"❌ DEBUG: Extension startup failed: {e}")
        
    def on_shutdown(self):
        print("🔧 DEBUG: Batch USD extension shutting down")
        
        if hasattr(self, '_api_service') and self._api_service:
            self._api_service.stop_server()
