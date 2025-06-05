import omni.ext
import logging
from typing import Dict, List, Optional
import asyncio

# Omniverse imports for scene manipulation
import omni.usd
import omni.kit.commands
from pxr import Usd, UsdGeom, Sdf, Gf
import carb
from pathlib import Path

logger = logging.getLogger(__name__)

class SceneObject:
    """Represents an object in the scene"""
    def __init__(self, name: str, object_type: str, prim_path: str, file_path: str = None):
        self.name = name
        self.object_type = object_type  # mesh, pointcloud, robot
        self.prim_path = prim_path
        self.file_path = file_path
        self.imported = False
        self.metadata = {}
    
    def to_dict(self):
        return {
            "name": self.name,
            "type": self.object_type,
            "prim_path": self.prim_path,
            "file_path": self.file_path,
            "imported": self.imported,
            "metadata": self.metadata
        }

class RoWorksSceneManager:
    """Enhanced scene manager with USD operations"""
    
    def __init__(self):
        self._scene_objects: Dict[str, SceneObject] = {}
        self.context = omni.usd.get_context()
        self._stage = None
        logger.info("RoWorks Scene Manager initialized with USD support")
    
    def get_stage(self) -> Optional[Usd.Stage]:
        """Get the current USD stage"""
        if not self._stage:
            self._stage = self.context.get_stage()
        return self._stage
    
    def add_scene_object(self, scene_object: SceneObject) -> bool:
        """Add a scene object to tracking"""
        try:
            self._scene_objects[scene_object.prim_path] = scene_object
            logger.info(f"Added scene object: {scene_object.name} at {scene_object.prim_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to add scene object: {e}")
            return False
    
    def get_scene_objects(self) -> Dict[str, SceneObject]:
        """Get all scene objects"""
        return self._scene_objects
    
    def get_scene_object(self, prim_path: str) -> Optional[SceneObject]:
        """Get a specific scene object"""
        return self._scene_objects.get(prim_path)
    
    def get_objects_by_type(self, object_type: str) -> List[SceneObject]:
        """Get all objects of a specific type"""
        return [obj for obj in self._scene_objects.values() if obj.object_type == object_type]
    
    def get_scene_stats(self) -> Dict:
        """Get scene statistics"""
        stats = {"total_objects": len(self._scene_objects)}
        by_type = {}
        
        for obj in self._scene_objects.values():
            by_type[obj.object_type] = by_type.get(obj.object_type, 0) + 1
        
        stats["objects_by_type"] = by_type
        stats["objects"] = [obj.to_dict() for obj in self._scene_objects.values()]
        
        return stats
    
    def import_mesh_file(self, file_path: str, file_name: str) -> Optional[SceneObject]:
        """Import a mesh file into the scene"""
        try:
            stage = self.get_stage()
            if not stage:
                logger.error("No USD stage available")
                return None
            
            # Generate safe prim path
            safe_name = Path(file_name).stem.replace(" ", "_").replace("-", "_")
            prim_path = f"/World/RoWorks/Meshes/{safe_name}"
            
            # Create scene object
            scene_obj = SceneObject(file_name, "mesh", prim_path, file_path)
            
            file_ext = Path(file_path).suffix.lower()
            
            if file_ext == '.obj':
                success = self._import_obj_file(file_path, prim_path, file_name)
            elif file_ext in ['.usd', '.usda', '.usdc']:
                success = self._import_usd_file(file_path, prim_path)
            elif file_ext == '.fbx':
                success = self._import_fbx_file(file_path, prim_path)
            else:
                success = self._create_mesh_placeholder(prim_path, file_name)
            
            if success:
                scene_obj.imported = True
                self.add_scene_object(scene_obj)
                logger.info(f"Successfully imported mesh: {file_name}")
                return scene_obj
            
            return None
            
        except Exception as e:
            logger.error(f"Error importing mesh {file_name}: {e}")
            return None
    
    def import_pointcloud_file(self, file_path: str, file_name: str) -> Optional[SceneObject]:
        """Import a point cloud file into the scene"""
        try:
            stage = self.get_stage()
            if not stage:
                return None
            
            safe_name = Path(file_name).stem.replace(" ", "_").replace("-", "_")
            prim_path = f"/World/RoWorks/PointClouds/{safe_name}"
            
            scene_obj = SceneObject(file_name, "pointcloud", prim_path, file_path)
            
            file_ext = Path(file_path).suffix.lower()
            
            if file_ext == '.xyz':
                success = self._import_xyz_pointcloud(file_path, prim_path, file_name)
            elif file_ext in ['.pcd', '.ply', '.las']:
                success = self._create_pointcloud_placeholder(prim_path, file_name)
            else:
                success = self._create_pointcloud_placeholder(prim_path, file_name)
            
            if success:
                scene_obj.imported = True
                self.add_scene_object(scene_obj)
                logger.info(f"Successfully imported point cloud: {file_name}")
                return scene_obj
            
            return None
            
        except Exception as e:
            logger.error(f"Error importing point cloud {file_name}: {e}")
            return None
    
    def import_robot_file(self, file_path: str, file_name: str) -> Optional[SceneObject]:
        """Import a robot file into the scene"""
        try:
            stage = self.get_stage()
            if not stage:
                return None
            
            safe_name = Path(file_name).stem.replace(" ", "_").replace("-", "_")
            prim_path = f"/World/RoWorks/Robots/{safe_name}"
            
            scene_obj = SceneObject(file_name, "robot", prim_path, file_path)
            
            file_ext = Path(file_path).suffix.lower()
            
            if file_ext in ['.urdf', '.xacro']:
                success = self._create_robot_placeholder(prim_path, file_name)
            elif file_ext in ['.usd', '.usda', '.usdc']:
                success = self._import_usd_file(file_path, prim_path)
            else:
                success = self._create_robot_placeholder(prim_path, file_name)
            
            if success:
                scene_obj.imported = True
                self.add_scene_object(scene_obj)
                logger.info(f"Successfully imported robot: {file_name}")
                return scene_obj
            
            return None
            
        except Exception as e:
            logger.error(f"Error importing robot {file_name}: {e}")
            return None
    
    def _import_obj_file(self, file_path: str, prim_path: str, file_name: str) -> bool:
        """Import OBJ file"""
        try:
            # Try using asset importer first
            try:
                success = omni.kit.commands.execute(
                    'CreateReference',
                    usd_context=self.context,
                    path_to=prim_path,
                    asset_path=file_path,
                    instanceable=False
                )
                if success:
                    return True
            except:
                pass
            
            # Fallback to placeholder
            return self._create_mesh_placeholder(prim_path, file_name)
            
        except Exception as e:
            logger.error(f"Error importing OBJ: {e}")
            return False
    
    def _import_usd_file(self, file_path: str, prim_path: str) -> bool:
        """Import USD file as reference"""
        try:
            success = omni.kit.commands.execute(
                'CreateReference',
                usd_context=self.context,
                path_to=prim_path,
                asset_path=file_path,
                instanceable=False
            )
            return success
        except Exception as e:
            logger.error(f"Error importing USD: {e}")
            return False
    
    def _import_fbx_file(self, file_path: str, prim_path: str) -> bool:
        """Import FBX file"""
        try:
            success = omni.kit.commands.execute(
                'CreateReference',
                usd_context=self.context,
                path_to=prim_path,
                asset_path=file_path,
                instanceable=False
            )
            return success
        except Exception as e:
            logger.error(f"Error importing FBX: {e}")
            return False
    
    def _create_mesh_placeholder(self, prim_path: str, file_name: str) -> bool:
        """Create a placeholder mesh"""
        try:
            stage = self.get_stage()
            
            # Create Xform for the mesh
            xform_prim = UsdGeom.Xform.Define(stage, prim_path)
            
            # Add metadata
            prim = xform_prim.GetPrim()
            prim.CreateAttribute("roworks:source_file", Sdf.ValueTypeNames.String).Set(file_name)
            prim.CreateAttribute("roworks:file_type", Sdf.ValueTypeNames.String).Set("mesh")
            
            # Create a cube as placeholder
            cube_path = prim_path + "/geometry"
            cube = UsdGeom.Cube.Define(stage, cube_path)
            cube.CreateSizeAttr(1.0)
            
            # Set a material color
            cube.CreateDisplayColorAttr([(0.8, 0.3, 0.3)])  # Red-ish color
            
            logger.info(f"Created mesh placeholder for: {file_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating mesh placeholder: {e}")
            return False
    
    def _import_xyz_pointcloud(self, file_path: str, prim_path: str, file_name: str) -> bool:
        """Import XYZ point cloud file"""
        try:
            stage = self.get_stage()
            
            # Read XYZ file (limit points for performance)
            points = []
            with open(file_path, 'r') as f:
                for line_num, line in enumerate(f):
                    if line_num > 50000:  # Limit for performance
                        break
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        try:
                            x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                            points.append((x, y, z))
                        except ValueError:
                            continue
            
            if points:
                # Create Xform parent
                xform_prim = UsdGeom.Xform.Define(stage, prim_path)
                prim = xform_prim.GetPrim()
                prim.CreateAttribute("roworks:source_file", Sdf.ValueTypeNames.String).Set(file_name)
                prim.CreateAttribute("roworks:file_type", Sdf.ValueTypeNames.String).Set("pointcloud")
                
                # Create UsdGeom Points
                points_geom = UsdGeom.Points.Define(stage, prim_path + "/points")
                points_geom.CreatePointsAttr(points)
                
                # Set display properties
                points_geom.CreateDisplayColorAttr([(1.0, 1.0, 1.0)])  # White points
                points_geom.CreateWidthsAttr([2.0] * len(points))  # Point size
                
                logger.info(f"Imported {len(points)} points from {file_name}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error importing XYZ file: {e}")
            return False
    
    def _create_pointcloud_placeholder(self, prim_path: str, file_name: str) -> bool:
        """Create a placeholder point cloud"""
        try:
            stage = self.get_stage()
            
            # Create Xform parent
            xform_prim = UsdGeom.Xform.Define(stage, prim_path)
            prim = xform_prim.GetPrim()
            prim.CreateAttribute("roworks:source_file", Sdf.ValueTypeNames.String).Set(file_name)
            prim.CreateAttribute("roworks:file_type", Sdf.ValueTypeNames.String).Set("pointcloud")
            
            # Create sample points
            sample_points = [
                (0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1),
                (1, 1, 0), (1, 0, 1), (0, 1, 1), (1, 1, 1),
                (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5)
            ]
            
            points_geom = UsdGeom.Points.Define(stage, prim_path + "/points")
            points_geom.CreatePointsAttr(sample_points)
            points_geom.CreateDisplayColorAttr([(0.3, 0.8, 1.0)])  # Light blue
            points_geom.CreateWidthsAttr([3.0] * len(sample_points))
            
            logger.info(f"Created point cloud placeholder for: {file_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating point cloud placeholder: {e}")
            return False
    
    def _create_robot_placeholder(self, prim_path: str, file_name: str) -> bool:
        """Create a placeholder robot structure"""
        try:
            stage = self.get_stage()
            
            # Create Xform parent
            xform_prim = UsdGeom.Xform.Define(stage, prim_path)
            prim = xform_prim.GetPrim()
            prim.CreateAttribute("roworks:source_file", Sdf.ValueTypeNames.String).Set(file_name)
            prim.CreateAttribute("roworks:file_type", Sdf.ValueTypeNames.String).Set("robot")
            
            # Create robot base
            base_path = prim_path + "/base"
            base_cube = UsdGeom.Cube.Define(stage, base_path)
            base_cube.CreateSizeAttr(0.8)
            base_cube.CreateDisplayColorAttr([(0.2, 0.2, 0.8)])  # Blue base
            
            # Create robot arm
            arm_path = prim_path + "/arm"
            arm_xform = UsdGeom.Xform.Define(stage, arm_path)
            arm_xform.AddTranslateOp().Set((0, 0, 0.6))
            
            arm_cylinder = UsdGeom.Cylinder.Define(stage, arm_path + "/cylinder")
            arm_cylinder.CreateRadiusAttr(0.15)
            arm_cylinder.CreateHeightAttr(1.2)
            arm_cylinder.CreateDisplayColorAttr([(0.8, 0.8, 0.2)])  # Yellow arm
            
            # Create end effector
            ee_path = prim_path + "/end_effector"
            ee_xform = UsdGeom.Xform.Define(stage, ee_path)
            ee_xform.AddTranslateOp().Set((0, 0, 1.4))
            
            ee_sphere = UsdGeom.Sphere.Define(stage, ee_path + "/sphere")
            ee_sphere.CreateRadiusAttr(0.1)
            ee_sphere.CreateDisplayColorAttr([(0.8, 0.2, 0.2)])  # Red end effector
            
            logger.info(f"Created robot placeholder for: {file_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating robot placeholder: {e}")
            return False
    
    async def clear_scene(self):
        """Clear all RoWorks objects from the scene"""
        try:
            stage = self.get_stage()
            if not stage:
                return False
            
            # Clear from USD stage
            cleared_count = 0
            for prim in stage.Traverse():
                if prim.HasAttribute("roworks:file_type"):
                    omni.kit.commands.execute('DeletePrims', paths=[str(prim.GetPath())])
                    cleared_count += 1
            
            # Clear from memory
            self._scene_objects.clear()
            
            logger.info(f"Cleared {cleared_count} RoWorks objects from scene")
            return True
            
        except Exception as e:
            logger.error(f"Error clearing scene: {e}")
            return False
    
    def remove_scene_object(self, prim_path: str) -> bool:
        """Remove a specific scene object"""
        try:
            stage = self.get_stage()
            if stage:
                omni.kit.commands.execute('DeletePrims', paths=[prim_path])
            
            if prim_path in self._scene_objects:
                del self._scene_objects[prim_path]
            
            logger.info(f"Removed scene object: {prim_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error removing scene object: {e}")
            return False

# Global variable to store scene manager (simple approach)
_global_scene_manager = None

class RoWorksSceneManagerExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        global _global_scene_manager
        logger.info("[roworks.scene.manager] Starting up")
        print("🚀 RoWorks Scene Manager Extension Started!")
        
        self._scene_manager = RoWorksSceneManager()
        _global_scene_manager = self._scene_manager
        
        print("📦 Scene Manager ready for 3D object import and management")
        
    def on_shutdown(self):
        global _global_scene_manager
        logger.info("[roworks.scene.manager] Shutting down")
        _global_scene_manager = None

def get_scene_manager() -> Optional[RoWorksSceneManager]:
    """Get the global scene manager instance"""
    return _global_scene_manager
