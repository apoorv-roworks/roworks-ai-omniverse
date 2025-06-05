import omni.ext
import logging
import asyncio
import threading
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pathlib import Path

logger = logging.getLogger(__name__)

class RoWorksAPIService:
    def __init__(self):
        self._app = FastAPI(
            title="RoWorks AI Omniverse API",
            description="REST API for 3D data import and scene management",
            version="1.0.0"
        )
        
        # Enable CORS
        self._app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        self._server = None
        self._server_thread = None
        self.scene_objects = []
        
        # Setup routes
        self._setup_routes()
        logger.info("RoWorks API Service initialized")
    
    def _setup_routes(self):
        """Setup API routes"""
        
        @self._app.get("/")
        async def root():
            return {
                "message": "RoWorks AI Omniverse API is running",
                "status": "active",
                "version": "1.0.0"
            }
            
        @self._app.get("/health")
        async def health_check():
            return {
                "status": "healthy",
                "api": "running",
                "scene_objects": len(self.scene_objects)
            }
                
        @self._app.get("/scene/info")
        async def get_scene_info():
            objects_by_type = {}
            for obj in self.scene_objects:
                obj_type = obj["type"]
                objects_by_type[obj_type] = objects_by_type.get(obj_type, 0) + 1
            
            return {
                "total_objects": len(self.scene_objects),
                "objects_by_type": objects_by_type,
                "objects": self.scene_objects
            }
                
        @self._app.post("/mesh/import")
        async def import_mesh(file: UploadFile = File(...)):
            try:
                # Read file content
                content = await file.read()
                
                # Create scene object
                obj = {
                    "name": file.filename,
                    "type": "mesh",
                    "prim_path": f"/World/Meshes/{Path(file.filename).stem}",
                    "file_size": len(content),
                    "source_file": file.filename
                }
                self.scene_objects.append(obj)
                
                logger.info(f"Imported mesh: {file.filename}")
                
                return {
                    "success": True,
                    "message": f"Mesh '{file.filename}' imported successfully",
                    "data": {
                        "prim_path": obj["prim_path"],
                        "name": obj["name"],
                        "object_type": "mesh"
                    }
                }
            except Exception as e:
                logger.error(f"Error importing mesh: {e}")
                return {
                    "success": False,
                    "message": f"Failed to import mesh: {str(e)}"
                }
            
        @self._app.post("/pointcloud/import")
        async def import_pointcloud(file: UploadFile = File(...)):
            try:
                content = await file.read()
                
                obj = {
                    "name": file.filename,
                    "type": "pointcloud",
                    "prim_path": f"/World/PointClouds/{Path(file.filename).stem}",
                    "file_size": len(content),
                    "source_file": file.filename
                }
                self.scene_objects.append(obj)
                
                logger.info(f"Imported point cloud: {file.filename}")
                
                return {
                    "success": True,
                    "message": f"Point cloud '{file.filename}' imported successfully",
                    "data": {
                        "prim_path": obj["prim_path"],
                        "name": obj["name"],
                        "object_type": "pointcloud"
                    }
                }
            except Exception as e:
                logger.error(f"Error importing point cloud: {e}")
                return {
                    "success": False,
                    "message": f"Failed to import point cloud: {str(e)}"
                }
            
        @self._app.post("/robot/import")
        async def import_robot(file: UploadFile = File(...)):
            try:
                content = await file.read()
                
                obj = {
                    "name": file.filename,
                    "type": "robot",
                    "prim_path": f"/World/Robots/{Path(file.filename).stem}",
                    "file_size": len(content),
                    "source_file": file.filename
                }
                self.scene_objects.append(obj)
                
                logger.info(f"Imported robot: {file.filename}")
                
                return {
                    "success": True,
                    "message": f"Robot '{file.filename}' imported successfully",
                    "data": {
                        "prim_path": obj["prim_path"],
                        "name": obj["name"],
                        "object_type": "robot"
                    }
                }
            except Exception as e:
                logger.error(f"Error importing robot: {e}")
                return {
                    "success": False,
                    "message": f"Failed to import robot: {str(e)}"
                }
                
        @self._app.delete("/scene/clear")
        async def clear_scene():
            try:
                self.scene_objects.clear()
                logger.info("Scene cleared")
                
                return {
                    "success": True,
                    "message": "Scene cleared successfully"
                }
            except Exception as e:
                logger.error(f"Error clearing scene: {e}")
                return {
                    "success": False,
                    "message": f"Failed to clear scene: {str(e)}"
                }
    
    def start_server(self):
        """Start the API server in a separate thread"""
        def run_server():
            try:
                config = uvicorn.Config(
                    app=self._app,
                    host="0.0.0.0",
                    port=49101,
                    log_level="info"
                )
                self._server = uvicorn.Server(config)
                logger.info("🌐 Starting RoWorks API server on port 49101")
                print("🌐 RoWorks API Server Starting on port 49101!")
                
                # Run the server
                asyncio.set_event_loop(asyncio.new_event_loop())
                asyncio.get_event_loop().run_until_complete(self._server.serve())
                
            except Exception as e:
                logger.error(f"Failed to start API server: {e}")
        
        # Start server in background thread
        self._server_thread = threading.Thread(target=run_server, daemon=True)
        self._server_thread.start()
    
    def stop_server(self):
        """Stop the API server"""
        if self._server:
            self._server.should_exit = True
            logger.info("RoWorks API server stopped")


class RoWorksServiceApiExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        logger.info("[roworks.service.api] Starting up")
        print("🚀 RoWorks Service API Extension Started!")
        
        self._api_service = RoWorksAPIService()
        
        # Start the API server
        self._api_service.start_server()
        
        logger.info("RoWorks API service initialized")
        
    def on_shutdown(self):
        logger.info("[roworks.service.api] Shutting down")
        
        if hasattr(self, '_api_service') and self._api_service:
            self._api_service.stop_server()
