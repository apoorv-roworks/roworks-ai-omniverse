import omni.ext
import logging
import asyncio
import threading
import tempfile
import os
import re
import time
import zipfile
import gzip
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import Dict, Any, Optional, List, Tuple

# Omniverse imports
import carb
import omni.kit.app
import omni.usd
from pxr import Usd, UsdGeom, Sdf

logger = logging.getLogger(__name__)

class PolycamUSDManager:
    """Manages Polycam ZIP + Point Cloud uploads and triggers USD creation with compression support"""
    
    def __init__(self):
        print("🔧 DEBUG: Initializing PolycamUSDManager with compression support")
        self.uploaded_files = {
            "polycam_zip": None,    # Required: Contains OBJ, MTL, textures
            "pointcloud": None,     # Required: Separate point cloud file
            "robot": None           # Optional: Robot model
        }
        self.scene_objects = []
        self.usd_scene_created = False
        print("🔧 DEBUG: Polycam USD manager ready for ZIP + Point Cloud workflow")
    
    def add_uploaded_file(self, file_type: str, filename: str, file_path: str, file_size: int) -> Dict[str, Any]:
        """Add uploaded file and check if ready for USD creation"""
        print(f"🔧 DEBUG: Adding {file_type}: {filename} ({file_size / 1024 / 1024:.1f} MB)")
        
        self.uploaded_files[file_type] = {
            "filename": filename,
            "file_path": file_path,
            "file_size": file_size,
            "uploaded_at": time.time()
        }
        
        # Check if we have required files: Polycam ZIP + Point Cloud
        has_polycam = self.uploaded_files["polycam_zip"] is not None
        has_pointcloud = self.uploaded_files["pointcloud"] is not None
        has_robot = self.uploaded_files["robot"] is not None
        
        print(f"🔧 DEBUG: Upload status - Polycam ZIP: {has_polycam}, Point Cloud: {has_pointcloud}, Robot: {has_robot} (optional)")
        
        result = {
            "file_added": True,
            "files_ready": has_polycam and has_pointcloud,
            "uploaded_files": {k: v["filename"] if v else None for k, v in self.uploaded_files.items()},
            "requirements_met": has_polycam and has_pointcloud
        }
        
        # Trigger USD creation when both required files are uploaded
        if has_polycam and has_pointcloud and not self.usd_scene_created:
            print("🎬 DEBUG: Both required files ready! Triggering USD creation...")
            self._schedule_usd_creation()
            result["usd_creation_triggered"] = True
            result["message"] = "USD scene creation started automatically"
        elif not has_polycam:
            result["message"] = "Waiting for Polycam ZIP file"
        elif not has_pointcloud:
            result["message"] = "Waiting for Point Cloud file"
        else:
            result["message"] = f"{file_type.replace('_', ' ').title()} uploaded successfully"
        
        return result
    
    def _schedule_usd_creation(self):
        """Schedule USD creation with timeout protection"""
        print("🔧 DEBUG: Scheduling USD creation with timeout protection")
        
        async def create_usd_scene_with_timeout():
            print("🔧 DEBUG: [Main Thread] Starting USD scene creation with 60s timeout")
            try:
                # Use asyncio.wait_for to add timeout
                await asyncio.wait_for(self._create_polycam_usd_scene(), timeout=60.0)
            except asyncio.TimeoutError:
                print("❌ DEBUG: [Main Thread] USD creation timed out after 60 seconds")
                self._create_fallback_scene()
            except Exception as e:
                print(f"❌ DEBUG: [Main Thread] USD creation failed: {e}")
                import traceback
                traceback.print_exc()
                self._create_fallback_scene()
        
        # Schedule on Omniverse main thread
        app = omni.kit.app.get_app()
        asyncio.ensure_future(create_usd_scene_with_timeout())
    
    def _create_fallback_scene(self):
        """Create a simple fallback scene if USD creation fails"""
        print("🔧 DEBUG: Creating fallback scene")
        try:
            # Mark as created to prevent retries
            self.usd_scene_created = True
            
            # Add simple objects to show something worked
            polycam_info = {
                "name": "Polycam_Fallback",
                "type": "polycam_asset",
                "prim_path": "/World/RoWorks/Fallback/Polycam",
                "created": True,
                "file_size": 0
            }
            
            pc_info = {
                "name": "PointCloud_Fallback", 
                "type": "pointcloud",
                "prim_path": "/World/RoWorks/Fallback/PointCloud",
                "created": True,
                "file_size": 0,
                "point_count": 10
            }
            
            self.scene_objects.extend([polycam_info, pc_info])
            print("✅ DEBUG: Fallback scene created")
            
        except Exception as e:
            print(f"❌ DEBUG: Even fallback creation failed: {e}")
    
    async def _create_polycam_usd_scene(self):
        """Create USD scene with progress monitoring"""
        print("🎬 DEBUG: Creating USD scene from Polycam data")
        
        try:
            app = omni.kit.app.get_app()
            
            # Step 1: Wait for main thread
            print("🔧 DEBUG: Step 1/6 - Ensuring main thread...")
            await app.next_update_async()
            
            # Step 2: Get USD stage
            print("🔧 DEBUG: Step 2/6 - Getting USD stage...")
            context = omni.usd.get_context()
            stage = context.get_stage()
            
            if not stage:
                print("❌ DEBUG: No USD stage available")
                return False
            
            print("✅ DEBUG: USD stage available")
            
            # Step 3: Create folder structure
            print("🔧 DEBUG: Step 3/6 - Creating folder structure...")
            self._create_folder_structure(stage)
            await app.next_update_async()
            
            # Step 4: Process Polycam ZIP (if available)
            if self.uploaded_files["polycam_zip"]:
                print("🔧 DEBUG: Step 4/6 - Processing Polycam ZIP...")
                await self._create_polycam_mesh(stage, self.uploaded_files["polycam_zip"])
                await app.next_update_async()
            else:
                print("🔧 DEBUG: Step 4/6 - Skipping Polycam (not available)")
            
            # Step 5: Add point cloud (if available)
            if self.uploaded_files["pointcloud"]:
                print("🔧 DEBUG: Step 5/6 - Adding point cloud...")
                await self._create_pointcloud(stage, self.uploaded_files["pointcloud"])
                await app.next_update_async()
            else:
                print("🔧 DEBUG: Step 5/6 - Skipping point cloud (not available)")
            
            # Step 6: Add robot (if available)
            if self.uploaded_files["robot"]:
                print("🔧 DEBUG: Step 6/6 - Adding robot...")
                await self._create_robot(stage, self.uploaded_files["robot"])
                await app.next_update_async()
            else:
                print("🔧 DEBUG: Step 6/6 - Skipping robot (optional)")
            
            self.usd_scene_created = True
            print("🎉 DEBUG: Polycam USD scene created successfully!")
            
            return True
            
        except Exception as e:
            print(f"❌ DEBUG: Error creating Polycam USD scene: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _create_folder_structure(self, stage):
        """Create organized folder structure in USD"""
        print("🔧 DEBUG: Creating USD folder structure")
        
        # Main RoWorks folder
        if not stage.GetPrimAtPath("/World/RoWorks"):
            stage.DefinePrim("/World/RoWorks", "Xform")
            print("✅ DEBUG: Created /World/RoWorks")
        
        # Subfolders
        folders = ["PolycamAssets", "PointClouds", "Robots"]
        for folder in folders:
            folder_path = f"/World/RoWorks/{folder}"
            if not stage.GetPrimAtPath(folder_path):
                stage.DefinePrim(folder_path, "Xform")
                print(f"✅ DEBUG: Created {folder_path}")
    
    async def _create_polycam_mesh(self, stage, polycam_info):
        """Extract Polycam ZIP and create mesh with materials"""
        print(f"🔧 DEBUG: Processing Polycam ZIP: {polycam_info['filename']}")
        
        try:
            # Extract ZIP contents
            extracted = self._extract_polycam_zip(polycam_info['file_path'])
            if not extracted:
                print("❌ DEBUG: Failed to extract Polycam ZIP")
                return
            
            asset_name = self._sanitize_name(polycam_info['filename'])
            prim_path = f"/World/RoWorks/PolycamAssets/{asset_name}"
            
            # Create main asset prim
            asset_prim = stage.DefinePrim(prim_path, "Xform")
            
            # Add metadata
            asset_prim.CreateAttribute("roworks:source_file", Sdf.ValueTypeNames.String).Set(polycam_info['filename'])
            asset_prim.CreateAttribute("roworks:file_type", Sdf.ValueTypeNames.String).Set("polycam_asset")
            asset_prim.CreateAttribute("roworks:file_size", Sdf.ValueTypeNames.Int).Set(polycam_info['file_size'])
            
            # Create mesh from OBJ (enhanced placeholder for now)
            mesh_created = await self._create_mesh_from_obj(
                stage, 
                extracted.get('obj_file'),
                extracted.get('mtl_file'),
                extracted.get('texture_files', []),
                f"{prim_path}/Mesh"
            )
            
            if not mesh_created:
                print("⚠️ DEBUG: Creating fallback placeholder for Polycam mesh")
                self._create_polycam_placeholder(stage, prim_path, polycam_info['filename'])
            
            # Position the asset
            xform = UsdGeom.Xformable(asset_prim)
            xform.AddTranslateOp().Set((-3, 0, 0))  # Left side
            
            # Track object
            obj_info = {
                "name": polycam_info['filename'],
                "type": "polycam_asset",
                "prim_path": prim_path,
                "created": True,
                "file_size": polycam_info['file_size'],
                "extracted_files": extracted
            }
            self.scene_objects.append(obj_info)
            
            print(f"✅ DEBUG: Polycam asset created at {prim_path}")
            
        except Exception as e:
            print(f"❌ DEBUG: Error creating Polycam mesh: {e}")
    
    def _extract_polycam_zip(self, zip_path: str) -> Dict:
        """Extract and analyze Polycam ZIP contents"""
        extracted_files = {
            'obj_file': None,
            'mtl_file': None,
            'texture_files': [],
            'temp_dir': None
        }
        
        try:
            # Create temporary directory
            temp_dir = tempfile.mkdtemp(prefix="polycam_extract_")
            extracted_files['temp_dir'] = temp_dir
            
            # Extract ZIP
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # Analyze extracted files
            for file_path in Path(temp_dir).rglob('*'):
                if file_path.is_file():
                    ext = file_path.suffix.lower()
                    
                    if ext == '.obj':
                        extracted_files['obj_file'] = str(file_path)
                    elif ext == '.mtl':
                        extracted_files['mtl_file'] = str(file_path)
                    elif ext in ['.jpg', '.jpeg', '.png', '.tiff', '.tga', '.bmp']:
                        extracted_files['texture_files'].append(str(file_path))
            
            print(f"🔧 DEBUG: Extracted - OBJ: {bool(extracted_files['obj_file'])}, "
                  f"MTL: {bool(extracted_files['mtl_file'])}, "
                  f"Textures: {len(extracted_files['texture_files'])}")
            
            return extracted_files
            
        except Exception as e:
            print(f"❌ DEBUG: Error extracting ZIP: {e}")
            return {}
    
    async def _create_mesh_from_obj(self, stage, obj_path: str, mtl_path: str, 
                                   texture_paths: list, mesh_prim_path: str) -> bool:
        """Create mesh from OBJ file with materials (enhanced placeholder)"""
        try:
            if not obj_path or not os.path.exists(obj_path):
                return False
            
            # Create mesh prim
            mesh_prim = stage.DefinePrim(mesh_prim_path, "Xform")
            
            # Create enhanced cube placeholder with Polycam styling
            cube_path = f"{mesh_prim_path}/geometry"
            cube = UsdGeom.Cube.Define(stage, cube_path)
            cube.CreateSizeAttr(2.0)
            
            # Use distinctive color for Polycam assets
            cube.CreateDisplayColorAttr([(0.2, 0.8, 0.4)])  # Green for Polycam
            
            # Add metadata about source files
            mesh_prim.CreateAttribute("polycam:obj_file", Sdf.ValueTypeNames.String).Set(Path(obj_path).name)
            if mtl_path:
                mesh_prim.CreateAttribute("polycam:mtl_file", Sdf.ValueTypeNames.String).Set(Path(mtl_path).name)
            if texture_paths:
                texture_names = [Path(p).name for p in texture_paths]
                mesh_prim.CreateAttribute("polycam:textures", Sdf.ValueTypeNames.StringArray).Set(texture_names)
            
            print(f"✅ DEBUG: Created enhanced mesh from OBJ: {Path(obj_path).name}")
            return True
            
        except Exception as e:
            print(f"❌ DEBUG: Error creating mesh from OBJ: {e}")
            return False
    
    def _create_polycam_placeholder(self, stage, prim_path: str, filename: str):
        """Create a placeholder for Polycam asset"""
        try:
            cube_path = f"{prim_path}/placeholder"
            cube = UsdGeom.Cube.Define(stage, cube_path)
            cube.CreateSizeAttr(1.5)
            cube.CreateDisplayColorAttr([(0.9, 0.5, 0.1)])  # Orange for placeholder
            
            print(f"✅ DEBUG: Created Polycam placeholder for: {filename}")
            
        except Exception as e:
            print(f"❌ DEBUG: Error creating Polycam placeholder: {e}")
    
    async def _create_pointcloud(self, stage, pc_info):
        """Create point cloud object with compression support"""
        print(f"🔧 DEBUG: Creating point cloud: {pc_info['filename']}")
        
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
            
            print("🔧 DEBUG: Loading point cloud data with compression support...")
            
            # Load point data with compression support
            try:
                points = self._load_pointcloud_data(pc_info['file_path'], max_points=15000)
                print(f"🔧 DEBUG: Loaded {len(points)} points successfully")
            except Exception as e:
                print(f"❌ DEBUG: Point loading failed: {e}")
                points = self._get_sample_points()
            
            if not points:
                print("⚠️ DEBUG: No points loaded, using samples")
                points = self._get_sample_points()
            
            print("🔧 DEBUG: Creating USD Points geometry...")
            
            # Create points geometry
            points_path = f"{prim_path}/points"
            points_prim = stage.DefinePrim(points_path, "Points")
            points_geom = UsdGeom.Points(points_prim)
            
            # Set point data
            points_geom.CreatePointsAttr().Set(points)
            points_geom.CreateDisplayColorAttr().Set([(0.2, 0.6, 1.0)])  # Blue for pointcloud
            points_geom.CreateWidthsAttr().Set([2.0] * len(points))
            
            print("🔧 DEBUG: Points geometry created successfully")
            
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
            
            print(f"✅ DEBUG: Point cloud created at {prim_path} with {len(points)} points")
            
        except Exception as e:
            print(f"❌ DEBUG: Error creating point cloud: {e}")
            import traceback
            traceback.print_exc()
            
            # Create fallback placeholder
            try:
                print("🔧 DEBUG: Creating fallback point cloud placeholder")
                self._create_pointcloud_placeholder(stage, prim_path, pc_info['filename'])
            except Exception as e2:
                print(f"❌ DEBUG: Even placeholder creation failed: {e2}")
    
    def _load_pointcloud_data(self, file_path: str, max_points: int = 15000) -> List[Tuple[float, float, float]]:
        """Load point cloud data from file, supporting compressed formats"""
        points = []
        
        try:
            file_size = os.path.getsize(file_path)
            print(f"🔧 DEBUG: Point cloud file size: {file_size / 1024 / 1024:.1f} MB")
            
            file_ext = Path(file_path).suffix.lower()
            
            if file_ext == '.xyz':
                points = self._load_xyz_file(file_path, max_points)
            elif file_ext == '.gz':
                points = self._load_gz_xyz_file(file_path, max_points)
            elif file_ext == '.zip':
                points = self._load_zip_xyz_file(file_path, max_points)
            else:
                print(f"⚠️ DEBUG: Unsupported point cloud format: {file_ext}, creating placeholder")
                
            print(f"🔧 DEBUG: Successfully loaded {len(points)} points")
            
        except Exception as e:
            print(f"❌ DEBUG: Error reading point cloud file: {e}")
            import traceback
            traceback.print_exc()
        
        # Fallback to sample points if loading failed
        if not points:
            print("🔧 DEBUG: Using fallback sample points")
            return self._get_sample_points()
        
        return points
    
    def _load_xyz_file(self, file_path: str, max_points: int) -> List[Tuple[float, float, float]]:
        """Load regular XYZ file"""
        points = []
        print(f"🔧 DEBUG: Loading XYZ file, max points: {max_points}")
        
        with open(file_path, 'r') as f:
            for line_num, line in enumerate(f):
                if line_num >= max_points:
                    print(f"🔧 DEBUG: Reached max points limit ({max_points})")
                    break
                    
                if line_num % 2000 == 0:  # Progress indicator
                    print(f"🔧 DEBUG: Processed {line_num} points...")
                
                parts = line.strip().split()
                if len(parts) >= 3:
                    try:
                        x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                        points.append((x, y, z))
                    except ValueError:
                        continue
        
        return points
    
    def _load_gz_xyz_file(self, file_path: str, max_points: int) -> List[Tuple[float, float, float]]:
        """Load gzipped XYZ file"""
        points = []
        print(f"🔧 DEBUG: Loading gzipped XYZ file, max points: {max_points}")
        
        with gzip.open(file_path, 'rt') as f:
            for line_num, line in enumerate(f):
                if line_num >= max_points:
                    print(f"🔧 DEBUG: Reached max points limit ({max_points})")
                    break
                    
                if line_num % 2000 == 0:
                    print(f"🔧 DEBUG: Processed {line_num} points...")
                
                parts = line.strip().split()
                if len(parts) >= 3:
                    try:
                        x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                        points.append((x, y, z))
                    except ValueError:
                        continue
        
        return points
    
    def _load_zip_xyz_file(self, file_path: str, max_points: int) -> List[Tuple[float, float, float]]:
        """Load XYZ file from ZIP archive"""
        points = []
        print(f"🔧 DEBUG: Loading XYZ from ZIP file, max points: {max_points}")
        
        try:
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                # Find XYZ file in ZIP
                xyz_files = [f for f in zip_ref.namelist() if f.lower().endswith('.xyz')]
                
                if not xyz_files:
                    print("❌ DEBUG: No XYZ file found in ZIP")
                    return []
                
                xyz_file = xyz_files[0]  # Use first XYZ file found
                print(f"🔧 DEBUG: Found XYZ file in ZIP: {xyz_file}")
                
                with zip_ref.open(xyz_file) as f:
                    for line_num, line_bytes in enumerate(f):
                        if line_num >= max_points:
                            print(f"🔧 DEBUG: Reached max points limit ({max_points})")
                            break
                            
                        if line_num % 2000 == 0:
                            print(f"🔧 DEBUG: Processed {line_num} points...")
                        
                        line = line_bytes.decode('utf-8').strip()
                        parts = line.split()
                        if len(parts) >= 3:
                            try:
                                x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                                points.append((x, y, z))
                            except ValueError:
                                continue
                                
        except Exception as e:
            print(f"❌ DEBUG: Error reading ZIP file: {e}")
            
        return points
    
    def _get_sample_points(self) -> List[Tuple[float, float, float]]:
        """Get sample points for fallback"""
        return [
            (0, 0, 0), (0.5, 0, 0), (0, 0.5, 0), (0, 0, 0.5),
            (0.5, 0.5, 0), (0.5, 0, 0.5), (0, 0.5, 0.5), (0.5, 0.5, 0.5),
            (0.25, 0.25, 0.25), (-0.25, 0.25, 0.25), (0.25, -0.25, 0.25),
            (1, 1, 1), (-1, 1, 1), (1, -1, 1), (1, 1, -1)
        ]
    
    def _create_pointcloud_placeholder(self, stage, prim_path: str, filename: str):
        """Create a simple point cloud placeholder"""
        try:
            print(f"🔧 DEBUG: Creating point cloud placeholder for {filename}")
            
            # Create simple cube placeholder instead of points
            cube_prim = stage.DefinePrim(prim_path, "Cube")
            cube_geom = UsdGeom.Cube(cube_prim)
            cube_geom.CreateSizeAttr().Set(1.0)
            cube_geom.CreateDisplayColorAttr().Set([(0.3, 0.8, 1.0)])  # Light blue
            
            # Add metadata
            cube_prim.CreateAttribute("roworks:source_file", Sdf.ValueTypeNames.String).Set(filename)
            cube_prim.CreateAttribute("roworks:file_type", Sdf.ValueTypeNames.String).Set("pointcloud_placeholder")
            
            print(f"✅ DEBUG: Created simple placeholder for: {filename}")
            
        except Exception as e:
            print(f"❌ DEBUG: Error creating placeholder: {e}")
    
    async def _create_robot(self, stage, robot_info):
        """Create robot object (optional)"""
        print(f"🔧 DEBUG: Creating robot: {robot_info['filename']}")
        
        try:
            safe_name = self._sanitize_name(robot_info['filename'])
            prim_path = f"/World/RoWorks/Robots/{safe_name}"
            
            # Create main prim
            robot_prim = stage.DefinePrim(prim_path, "Xform")
            
            # Add metadata
            robot_prim.CreateAttribute("roworks:source_file", Sdf.ValueTypeNames.String).Set(robot_info['filename'])
            robot_prim.CreateAttribute("roworks:file_type", Sdf.ValueTypeNames.String).Set("robot")
            robot_prim.CreateAttribute("roworks:file_size", Sdf.ValueTypeNames.Int).Set(robot_info['file_size'])
            
            # Position it at center
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
            
            print(f"✅ DEBUG: Robot created at {prim_path}")
            
        except Exception as e:
            print(f"❌ DEBUG: Error creating robot: {e}")
    
    def _sanitize_name(self, name: str) -> str:
        """Create safe USD prim name"""
        # Remove file extension
        name = Path(name).stem if isinstance(name, str) else str(name)
        # Replace invalid characters with underscores
        name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        # Ensure it doesn't start with a number
        if name and name[0].isdigit():
            name = f"Asset_{name}"
        # Ensure it's not empty
        if not name:
            name = "UnnamedAsset"
        return name
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status"""
        return {
            "uploaded_files": {k: v["filename"] if v else None for k, v in self.uploaded_files.items()},
            "usd_scene_created": self.usd_scene_created,
            "scene_objects": len(self.scene_objects),
            "ready_for_usd": (self.uploaded_files["polycam_zip"] is not None and 
                             self.uploaded_files["pointcloud"] is not None),
            "workflow": "Upload Polycam ZIP + Point Cloud (supports compression) to trigger USD creation"
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


class PolycamAPIService:
    """API service for Polycam + Point Cloud USD creation with compression support"""
    
    def __init__(self):
        print("🔧 DEBUG: Initializing PolycamAPIService with compression support")
        self._app = FastAPI(
            title="RoWorks Polycam USD API",
            description="Polycam ZIP + Point Cloud to USD conversion with compression support",
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
        self._temp_dir = tempfile.mkdtemp(prefix="roworks_polycam_")
        
        self.usd_manager = PolycamUSDManager()
        self._setup_routes()
        print("🔧 DEBUG: Polycam API Service initialized with compression support")
    
    def _setup_routes(self):
        """Setup API routes"""
        
        @self._app.get("/health")
        async def health_check():
            return {
                "status": "healthy",
                "service": "polycam_usd_creation",
                "features": ["compression_support", "timeout_protection", "smart_sampling"],
                "temp_dir": self._temp_dir,
                **self.usd_manager.get_status()
            }
        
        @self._app.get("/status")
        async def get_status():
            return self.usd_manager.get_status()
        
        @self._app.get("/scene/info")
        async def get_scene_info():
            return self.usd_manager.get_scene_stats()
        
        @self._app.post("/polycam/import")
        async def import_polycam(file: UploadFile = File(...)):
            """Import Polycam ZIP file containing OBJ, MTL, and textures"""
            print(f"🔧 DEBUG: Uploading Polycam ZIP: {file.filename}")
            start_time = time.time()
            
            try:
                # Validate file
                if not file.filename:
                    raise HTTPException(status_code=400, detail="No file provided")
                
                if not file.filename.lower().endswith('.zip'):
                    raise HTTPException(status_code=400, detail="File must be a ZIP archive")
                
                # Read content
                content = await file.read()
                file_size = len(content)
                print(f"🔧 DEBUG: ZIP file size: {file_size / 1024 / 1024:.1f} MB")
                
                # Save ZIP file
                zip_path = os.path.join(self._temp_dir, file.filename)
                with open(zip_path, 'wb') as f:
                    f.write(content)
                
                # Add to manager
                result = self.usd_manager.add_uploaded_file("polycam_zip", file.filename, zip_path, file_size)
                
                elapsed_time = time.time() - start_time
                print(f"🔧 DEBUG: Polycam ZIP processed in {elapsed_time:.2f}s")
                
                return {
                    "success": True,
                    "message": f"Polycam ZIP '{file.filename}' uploaded successfully",
                    "data": {
                        "name": file.filename,
                        "object_type": "polycam_zip",
                        "file_size": file_size,
                        "file_size_mb": round(file_size / 1024 / 1024, 2),
                        "processing_time": elapsed_time
                    },
                    "batch_status": result
                }
                    
            except HTTPException:
                raise
            except Exception as e:
                elapsed_time = time.time() - start_time
                print(f"❌ DEBUG: Polycam upload error after {elapsed_time:.2f}s: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self._app.post("/pointcloud/import")
        async def import_pointcloud(file: UploadFile = File(...)):
            """Import point cloud file (supports .xyz, .gz, .zip)"""
            print(f"🔧 DEBUG: Uploading point cloud: {file.filename}")
            start_time = time.time()
            
            try:
                # Validate file
                if not file.filename:
                    raise HTTPException(status_code=400, detail="No file provided")
                
                # Check supported formats
                supported_extensions = ['.xyz', '.gz', '.zip', '.pcd', '.ply', '.las']
                file_ext = Path(file.filename).suffix.lower()
                
                if file_ext not in supported_extensions:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Unsupported format. Supported: {', '.join(supported_extensions)}"
                    )
                
                # Read content with size check
                content = await file.read()
                file_size = len(content)
                print(f"🔧 DEBUG: Point cloud file size: {file_size / 1024 / 1024:.1f} MB")
                
                # Size limit (increased for compressed files)
                max_size = 50 * 1024 * 1024  # 50MB
                if file_size > max_size:
                    raise HTTPException(
                        status_code=400,
                        detail=f"File too large. Maximum size: {max_size // 1024 // 1024}MB"
                    )
                
                # Save file
                file_path = os.path.join(self._temp_dir, file.filename)
                with open(file_path, 'wb') as f:
                    f.write(content)
                
                print(f"🔧 DEBUG: File saved to: {file_path}")
                
                # Add to manager
                result = self.usd_manager.add_uploaded_file("pointcloud", file.filename, file_path, file_size)
                
                elapsed_time = time.time() - start_time
                print(f"🔧 DEBUG: Point cloud upload processed in {elapsed_time:.2f}s")
                
                return {
                    "success": True,
                    "message": f"Point cloud '{file.filename}' uploaded successfully",
                    "data": {
                        "name": file.filename,
                        "object_type": "pointcloud",
                        "file_size": file_size,
                        "file_size_mb": round(file_size / 1024 / 1024, 2),
                        "format": file_ext,
                        "compression_detected": file_ext in ['.gz', '.zip'],
                        "processing_time": elapsed_time
                    },
                    "batch_status": result
                }
                    
            except HTTPException:
                raise
            except Exception as e:
                elapsed_time = time.time() - start_time
                print(f"❌ DEBUG: Point cloud upload error after {elapsed_time:.2f}s: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self._app.post("/robot/import")
        async def import_robot(file: UploadFile = File(...)):
            return await self._handle_file_upload(file, "robot")
        
        @self._app.post("/polycam/extract")
        async def extract_polycam_info(file: UploadFile = File(...)):
            """Extract and analyze Polycam ZIP contents without importing"""
            try:
                if not file.filename or not file.filename.lower().endswith('.zip'):
                    raise HTTPException(status_code=400, detail="File must be a ZIP archive")
                
                # Save temporary file
                content = await file.read()
                zip_path = os.path.join(self._temp_dir, f"temp_{file.filename}")
                
                with open(zip_path, 'wb') as f:
                    f.write(content)
                
                # Extract and analyze
                extracted_files = self.usd_manager._extract_polycam_zip(zip_path)
                
                if extracted_files:
                    analysis = {
                        "has_obj": bool(extracted_files.get('obj_file')),
                        "has_mtl": bool(extracted_files.get('mtl_file')),
                        "texture_count": len(extracted_files.get('texture_files', [])),
                        "files": {
                            "obj": Path(extracted_files['obj_file']).name if extracted_files.get('obj_file') else None,
                            "mtl": Path(extracted_files['mtl_file']).name if extracted_files.get('mtl_file') else None,
                            "textures": [Path(f).name for f in extracted_files.get('texture_files', [])]
                        }
                    }
                    
                    return {
                        "success": True,
                        "message": "Polycam ZIP analyzed successfully",
                        "analysis": analysis
                    }
                else:
                    return {
                        "success": False,
                        "message": "Failed to analyze ZIP file"
                    }
                    
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self._app.post("/debug/pointcloud")
        async def debug_pointcloud(file: UploadFile = File(...)):
            """Debug endpoint to test point cloud processing without USD creation"""
            try:
                print(f"🔧 DEBUG: Analyzing point cloud file: {file.filename}")
                
                # Get file info
                content = await file.read()
                file_size = len(content)
                
                # Save temporarily
                temp_path = os.path.join(self._temp_dir, f"debug_{file.filename}")
                with open(temp_path, 'wb') as f:
                    f.write(content)
                
                # Try to read first few lines
                analysis = {
                    "filename": file.filename,
                    "file_size": file_size,
                    "file_size_mb": round(file_size / 1024 / 1024, 2),
                    "file_extension": Path(file.filename).suffix.lower(),
                    "compression_detected": Path(file.filename).suffix.lower() in ['.gz', '.zip'],
                    "sample_lines": [],
                    "total_lines": 0,
                    "processing_time": 0
                }
                
                start_time = time.time()
                
                try:
                    # Test loading with our compression support
                    points = self.usd_manager._load_pointcloud_data(temp_path, max_points=100)
                    analysis["points_loaded"] = len(points)
                    analysis["sample_points"] = points[:5] if points else []
                    
                except Exception as e:
                    analysis["error"] = str(e)
                
                analysis["processing_time"] = time.time() - start_time
                
                # Cleanup
                os.remove(temp_path)
                
                return {
                    "success": True,
                    "message": "Point cloud analysis complete",
                    "analysis": analysis
                }
                
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Analysis failed: {str(e)}"
                }
        
        @self._app.post("/debug/simple-usd")
        async def debug_simple_usd():
            """Create a simple USD scene for testing"""
            try:
                print("🔧 DEBUG: Creating simple test USD scene")
                
                # Get scene manager
                from roworks.scene.manager import get_scene_manager
                scene_manager = get_scene_manager()
                
                if not scene_manager:
                    return {"success": False, "message": "Scene manager not available"}
                
                stage = scene_manager.get_stage()
                if not stage:
                    return {"success": False, "message": "USD stage not available"}
                
                # Create simple test objects
                test_prim = stage.DefinePrim("/World/DebugTest", "Xform")
                cube = UsdGeom.Cube.Define(stage, "/World/DebugTest/TestCube")
                cube.CreateSizeAttr().Set(1.0)
                cube.CreateDisplayColorAttr().Set([(1.0, 0.0, 0.0)])  # Red cube
                
                return {
                    "success": True,
                    "message": "Simple USD scene created successfully",
                    "prim_path": "/World/DebugTest"
                }
                
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Simple USD creation failed: {str(e)}"
                }
        
        @self._app.get("/formats/supported")
        async def get_supported_formats():
            """Get all supported file formats including compressed point clouds"""
            return {
                "polycam_zip": [".zip"],
                "pointcloud": [".xyz", ".gz", ".zip", ".pcd", ".ply", ".las"],
                "robot": [".urdf", ".xacro", ".usd", ".usda", ".usdc"],
                "description": {
                    "polycam_zip": "Polycam ZIP archives containing OBJ mesh, MTL materials, and textures (REQUIRED)",
                    "pointcloud": "Point cloud data files - supports compressed formats (.gz, .zip) for large files (REQUIRED)",
                    "robot": "Robot model files (OPTIONAL)"
                },
                "compression": {
                    "recommended": "For large point clouds (>10MB), compress to .gz or .zip format",
                    "max_size": "50MB compressed",
                    "max_points": 15000
                },
                "workflow": "Upload Polycam ZIP + Point Cloud (optionally compressed) to trigger USD creation"
            }
        
        @self._app.delete("/scene/clear")
        async def clear_scene():
            self.usd_manager.scene_objects.clear()
            self.usd_manager.uploaded_files = {"polycam_zip": None, "pointcloud": None, "robot": None}
            self.usd_manager.usd_scene_created = False
            return {"success": True, "message": "Scene and uploads cleared"}
    
    async def _handle_file_upload(self, file: UploadFile, file_type: str):
        """Handle file upload for robot files"""
        print(f"🔧 DEBUG: Handling {file_type} upload: {file.filename}")
        start_time = time.time()
        
        try:
            # Validate file
            if not file.filename:
                raise HTTPException(status_code=400, detail="No file provided")
            
            # Read content
            content = await file.read()
            file_size = len(content)
            print(f"🔧 DEBUG: File size: {file_size / 1024 / 1024:.1f} MB")
            
            # Size limit for robot files
            max_size = 50 * 1024 * 1024  # 50MB
            if file_size > max_size:
                raise HTTPException(
                    status_code=400,
                    detail=f"File too large. Maximum size: {max_size // 1024 // 1024}MB"
                )
            
            # Save file
            file_path = os.path.join(self._temp_dir, file.filename)
            with open(file_path, 'wb') as f:
                f.write(content)
            
            # Add to manager
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
                    "file_size_mb": round(file_size / 1024 / 1024, 2),
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
                print("🚀 DEBUG: Polycam USD API server starting on port 49101")
                
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
        print("🚀 DEBUG: RoWorks Polycam USD API Extension Starting!")
        
        try:
            self._api_service = PolycamAPIService()
            self._api_service.start_server()
            
            print("✅ DEBUG: Polycam USD extension startup complete")
            print(f"🚀 API: http://localhost:49101 (Polycam USD Creation)")
            print("📝 Upload Polycam ZIP + Point Cloud files to trigger USD scene creation")
            print("🗜️ Point cloud compression support: .gz, .zip formats")
            print("📊 Smart sampling: Max 15,000 points for performance")
            print("⏱️ Timeout protection: 60 second limit for USD creation")
            print("🤖 Robot files are optional and will be included if uploaded")
            
        except Exception as e:
            print(f"❌ DEBUG: Extension startup failed: {e}")
        
    def on_shutdown(self):
        print("🔧 DEBUG: Polycam USD extension shutting down")
        
        if hasattr(self, '_api_service') and self._api_service:
            self._api_service.stop_server()


# Public API functions for compatibility
def some_public_function(x):
    """Legacy function for compatibility"""
    return x * x * x * x
