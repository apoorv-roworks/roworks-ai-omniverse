import omni.ext
import logging
from pathlib import Path
from typing import Optional
import asyncio

# Import our scene manager
from roworks.scene.manager import get_scene_manager

logger = logging.getLogger(__name__)

class FileImporter:
    """Handles importing different file types"""
    
    SUPPORTED_MESH_FORMATS = ['.obj', '.fbx', '.usd', '.usda', '.usdc']
    SUPPORTED_POINTCLOUD_FORMATS = ['.xyz', '.pcd', '.ply', '.las']
    SUPPORTED_ROBOT_FORMATS = ['.urdf', '.xacro', '.usd', '.usda', '.usdc']
    
    @staticmethod
    def get_file_type(file_path: str) -> Optional[str]:
        """Determine file type based on extension"""
        ext = Path(file_path).suffix.lower()
        
        if ext in FileImporter.SUPPORTED_MESH_FORMATS:
            return "mesh"
        elif ext in FileImporter.SUPPORTED_POINTCLOUD_FORMATS:
            return "pointcloud"
        elif ext in FileImporter.SUPPORTED_ROBOT_FORMATS and ext != '.usd':  # USD could be mesh or robot
            return "robot"
        elif ext in ['.usd', '.usda', '.usdc']:
            # For USD files, we need additional logic to determine type
            # For now, default to mesh
            return "mesh"
        else:
            return None
    
    @staticmethod
    def is_supported_file(file_path: str) -> bool:
        """Check if file type is supported"""
        return FileImporter.get_file_type(file_path) is not None
    
    @staticmethod
    def validate_file(file_path: str) -> tuple[bool, str]:
        """Validate file exists and is supported"""
        path = Path(file_path)
        
        if not path.exists():
            return False, f"File does not exist: {file_path}"
        
        if not path.is_file():
            return False, f"Path is not a file: {file_path}"
        
        if path.stat().st_size == 0:
            return False, f"File is empty: {file_path}"
        
        if not FileImporter.is_supported_file(file_path):
            return False, f"Unsupported file format: {path.suffix}"
        
        return True, "File is valid"

class RoWorksDataImporter:
    """Main data import handler"""
    
    def __init__(self):
        self.scene_manager = None
        logger.info("RoWorks Data Importer initialized")
    
    def _get_scene_manager(self):
        """Get scene manager instance"""
        if not self.scene_manager:
            self.scene_manager = get_scene_manager()
        return self.scene_manager
    
    def import_file(self, file_path: str, file_name: str = None) -> tuple[bool, str, dict]:
        """
        Import a file into the scene
        
        Returns:
            tuple: (success, message, data)
        """
        try:
            # Validate file
            is_valid, validation_msg = FileImporter.validate_file(file_path)
            if not is_valid:
                return False, validation_msg, {}
            
            # Get scene manager
            scene_manager = self._get_scene_manager()
            if not scene_manager:
                return False, "Scene manager not available", {}
            
            # Use filename if not provided
            if not file_name:
                file_name = Path(file_path).name
            
            # Determine file type
            file_type = FileImporter.get_file_type(file_path)
            if not file_type:
                return False, f"Unsupported file type: {Path(file_path).suffix}", {}
            
            logger.info(f"Importing {file_type}: {file_name}")
            
            # Import based on type
            scene_object = None
            if file_type == "mesh":
                scene_object = scene_manager.import_mesh_file(file_path, file_name)
            elif file_type == "pointcloud":
                scene_object = scene_manager.import_pointcloud_file(file_path, file_name)
            elif file_type == "robot":
                scene_object = scene_manager.import_robot_file(file_path, file_name)
            
            if scene_object:
                data = scene_object.to_dict()
                return True, f"Successfully imported {file_type}: {file_name}", data
            else:
                return False, f"Failed to import {file_type}: {file_name}", {}
                
        except Exception as e:
            logger.error(f"Error importing file {file_path}: {e}")
            return False, f"Import error: {str(e)}", {}
    
    def import_mesh(self, file_path: str, file_name: str = None) -> tuple[bool, str, dict]:
        """Import a mesh file"""
        ext = Path(file_path).suffix.lower()
        if ext not in FileImporter.SUPPORTED_MESH_FORMATS:
            return False, f"Unsupported mesh format: {ext}", {}
        
        return self.import_file(file_path, file_name)
    
    def import_pointcloud(self, file_path: str, file_name: str = None) -> tuple[bool, str, dict]:
        """Import a point cloud file"""
        ext = Path(file_path).suffix.lower()
        if ext not in FileImporter.SUPPORTED_POINTCLOUD_FORMATS:
            return False, f"Unsupported point cloud format: {ext}", {}
        
        return self.import_file(file_path, file_name)
    
    def import_robot(self, file_path: str, file_name: str = None) -> tuple[bool, str, dict]:
        """Import a robot file"""
        ext = Path(file_path).suffix.lower()
        if ext not in FileImporter.SUPPORTED_ROBOT_FORMATS:
            return False, f"Unsupported robot format: {ext}", {}
        
        return self.import_file(file_path, file_name)
    
    def get_supported_formats(self) -> dict:
        """Get all supported file formats"""
        return {
            "mesh": FileImporter.SUPPORTED_MESH_FORMATS,
            "pointcloud": FileImporter.SUPPORTED_POINTCLOUD_FORMATS,
            "robot": FileImporter.SUPPORTED_ROBOT_FORMATS
        }
    
    def get_scene_stats(self) -> dict:
        """Get current scene statistics"""
        scene_manager = self._get_scene_manager()
        if scene_manager:
            return scene_manager.get_scene_stats()
        return {"total_objects": 0, "objects_by_type": {}, "objects": []}

# Global data importer instance
_global_data_importer = None

class RoWorksDataImportExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        global _global_data_importer
        logger.info("[roworks.data.import] Starting up")
        print("🚀 RoWorks Data Import Extension Started!")
        
        self._data_importer = RoWorksDataImporter()
        _global_data_importer = self._data_importer
        
        print("📁 Data Import ready for mesh, point cloud, and robot files")
        
    def on_shutdown(self):
        global _global_data_importer
        logger.info("[roworks.data.import] Shutting down")
        _global_data_importer = None

def get_data_importer() -> Optional[RoWorksDataImporter]:
    """Get the global data importer instance"""
    return _global_data_importer

# Public API functions
def some_public_function(x):
    """Legacy function for compatibility"""
    return x * x * x * x
