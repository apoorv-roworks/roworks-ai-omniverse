# Complete Service API Extension for RoWorks AI Omniverse - With All Fixes
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


class USDAnalyzer:
    """Quick USD file analyzer to prevent hanging imports"""
    
    @staticmethod
    def quick_usd_check(usd_path: str) -> Tuple[bool, str]:
        """Quick check if USD file might cause hanging"""
        try:
            if not os.path.exists(usd_path):
                return False, "File does not exist"
            
            # File size check
            file_size_mb = os.path.getsize(usd_path) / (1024 * 1024)
            if file_size_mb > 200:
                return False, f"Large USD file ({file_size_mb:.1f}MB) may cause hanging"
            
            # Try to open stage quickly
            stage = Usd.Stage.Open(usd_path)
            if not stage:
                return False, "Cannot open USD stage"
            
            # Quick prim count check
            prim_count = len(list(stage.TraverseAll()))
            if prim_count > 15000:
                return False, f"High prim count ({prim_count}) may cause hanging"
            
            # Check for extremely complex meshes
            vertex_count = 0
            for prim in stage.Traverse():
                if prim.IsA(UsdGeom.Mesh):
                    mesh = UsdGeom.Mesh(prim)
                    points_attr = mesh.GetPointsAttr()
                    if points_attr:
                        points = points_attr.Get()
                        if points:
                            vertex_count += len(points)
                            if vertex_count > 2000000:  # 2M vertices
                                return False, f"High vertex count ({vertex_count}) may cause hanging"
            
            print(f"✅ USD file looks OK ({file_size_mb:.1f}MB, {prim_count} prims, {vertex_count} vertices)")
            return True, "File appears safe to import"
            
        except Exception as e:
            return False, f"USD check error: {str(e)}"


class NonBlockingUSDImporter:
    """Simplified non-blocking USD importer"""
    
    def __init__(self):
        self.import_queue = []
        self.is_importing = False
        self.import_timeout = 30.0  # 30 seconds
        
    def schedule_import(self, usd_path: str, asset_name: str, callback=None):
        """Schedule USD import without blocking"""
        # Quick safety check first
        is_safe, message = USDAnalyzer.quick_usd_check(usd_path)
        if not is_safe:
            print(f"❌ USD import rejected: {message}")
            if callback:
                callback(False, asset_name, message)
            return None
        
        import_task = {
            "usd_path": usd_path,
            "asset_name": asset_name,
            "callback": callback,
            "status": "queued"
        }
        
        self.import_queue.append(import_task)
        
        # Start processing if not already running
        if not self.is_importing:
            asyncio.ensure_future(self._process_import_queue())
            
        print(f"🔧 USD import queued: {asset_name}")
        return import_task
    
    async def _process_import_queue(self):
        """Process import queue with proper async handling"""
        if self.is_importing:
            return
            
        self.is_importing = True
        app = omni.kit.app.get_app()
        
        try:
            while self.import_queue:
                task = self.import_queue.pop(0)
                
                print(f"🔧 Processing USD import: {task['asset_name']}")
                task["status"] = "processing"
                
                try:
                    success, error_msg = await self._import_via_reference(
                        task["usd_path"], 
                        task["asset_name"]
                    )
                    
                    if success:
                        task["status"] = "completed"
                        print(f"✅ USD import completed: {task['asset_name']}")
                        
                        if task["callback"]:
                            task["callback"](True, task["asset_name"], "Import successful")
                    else:
                        task["status"] = "failed"
                        print(f"❌ USD import failed: {task['asset_name']} - {error_msg}")
                        
                        if task["callback"]:
                            task["callback"](False, task["asset_name"], error_msg)
                    
                    # Yield control between imports
                    await app.next_update_async()
                    await asyncio.sleep(0.2)  # Brief pause between imports
                    
                except Exception as e:
                    print(f"❌ USD import error: {e}")
                    task["status"] = "error"
                    
                    if task["callback"]:
                        task["callback"](False, task["asset_name"], str(e))
                    
                    continue
                    
        finally:
            self.is_importing = False
    
    async def _import_via_reference(self, usd_path: str, asset_name: str) -> Tuple[bool, str]:
        """Import by adding USD as reference to current stage"""
        try:
            app = omni.kit.app.get_app()
            context = omni.usd.get_context()
            
            # Apply timeout to the entire import process
            success, error = await asyncio.wait_for(
                self._do_reference_import(context, usd_path, asset_name),
                timeout=self.import_timeout
            )
            
            return success, error
            
        except asyncio.TimeoutError:
            return False, f"Import timeout after {self.import_timeout} seconds"
        except Exception as e:
            return False, f"Import error: {str(e)}"
    
    async def _do_reference_import(self, context, usd_path: str, asset_name: str) -> Tuple[bool, str]:
        """Actual reference import implementation"""
        app = omni.kit.app.get_app()
        
        stage = context.get_stage()
        if not stage:
            # Create new stage if none exists
            context.new_stage()
            await app.next_update_async()
            stage = context.get_stage()
            
            if not stage:
                return False, "Cannot get or create stage"
        
        # Create safe prim path
        safe_name = self._sanitize_name(asset_name)
        prim_path = f"/World/RoWorks/Assets/{safe_name}"
        
        print(f"🔧 Creating reference at: {prim_path}")
        
        # Ensure parent path exists
        await self._ensure_path_exists(stage, "/World/RoWorks/Assets")
        await app.next_update_async()
        
        # Remove existing prim if it exists
        if stage.GetPrimAtPath(prim_path):
            stage.RemovePrim(prim_path)
            await app.next_update_async()
        
        # Create prim and add reference
        prim = stage.DefinePrim(prim_path, "Xform")
        await app.next_update_async()
        
        # Add reference
        print("🔧 Adding USD reference...")
        prim.GetReferences().AddReference(usd_path)
        await app.next_update_async()
        
        # Add metadata
        prim.CreateAttribute("roworks:source_file", Sdf.ValueTypeNames.String).Set(usd_path)
        prim.CreateAttribute("roworks:asset_type", Sdf.ValueTypeNames.String).Set("usd_asset")
        await app.next_update_async()
        
        print(f"✅ USD reference added: {prim_path}")
        return True, "Reference created successfully"
    
    async def _ensure_path_exists(self, stage, path: str):
        """Ensure USD path exists"""
        parts = path.strip('/').split('/')
        current_path = ""
        
        for part in parts:
            current_path += f"/{part}"
            if not stage.GetPrimAtPath(current_path):
                stage.DefinePrim(current_path, "Xform")
    
    def _sanitize_name(self, name: str) -> str:
        """Create safe USD prim name"""
        name = Path(name).stem if isinstance(name, str) else str(name)
        name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        if name and name[0].isdigit():
            name = f"Asset_{name}"
        return name or "UnnamedAsset"
    
    def get_status(self) -> Dict[str, Any]:
        """Get importer status"""
        return {
            "queue_length": len(self.import_queue),
            "is_importing": self.is_importing,
            "queued_imports": [task["asset_name"] for task in self.import_queue]
        }


class MeshUSDManager:
    """Manages mesh ZIP uploads (OBJ+MTL+textures) and creates USD assets with texture fixes"""
    
    def __init__(self):
        print("🔧 DEBUG: Initializing MeshUSDManager for OBJ+MTL+texture workflow")
        self.uploaded_assets = []
        self.temp_dir = tempfile.mkdtemp(prefix="roworks_mesh_")
        self.usd_importer = NonBlockingUSDImporter()
        
        # Use existing scene manager if available
        self.scene_manager = None
        try:
            from roworks.scene.manager import get_scene_manager
            self.scene_manager = get_scene_manager()
            if self.scene_manager:
                print("✅ DEBUG: Connected to existing scene manager")
            else:
                print("⚠️ DEBUG: Scene manager available but not initialized")
        except ImportError:
            print("⚠️ DEBUG: Scene manager not available, using internal tracking")
        except Exception as e:
            print(f"⚠️ DEBUG: Error connecting to scene manager: {e}")
            
        print("🔧 DEBUG: Mesh USD manager ready for ZIP workflow")
    
    def process_mesh_zip(self, zip_path: str, filename: str, file_size: int) -> Dict[str, Any]:
        """Process mesh ZIP and create USD asset"""
        print(f"🔧 DEBUG: Processing mesh ZIP: {filename} ({file_size / 1024 / 1024:.1f} MB)")
        
        try:
            # Extract and validate ZIP contents
            extracted = self._extract_and_validate_zip(zip_path, filename)
            if not extracted['valid']:
                return {
                    "success": False,
                    "message": extracted['error'],
                    "asset": None
                }
            
            # Create USD asset
            asset_name = self._sanitize_name(filename)
            usd_result = self._create_usd_asset(extracted, asset_name, filename, file_size)
            
            if usd_result['success']:
                # Schedule USD import
                self._schedule_usd_import(usd_result['usd_path'], asset_name)
                
                # Track the asset
                asset_info = {
                    "filename": filename,
                    "asset_name": asset_name,
                    "file_size": file_size,
                    "usd_path": usd_result['usd_path'],
                    "extracted_files": extracted['files'],
                    "created_at": time.time(),
                    "imported_to_scene": False,
                    "import_status": "scheduled",
                    "import_message": "Import scheduled"
                }
                self.uploaded_assets.append(asset_info)
                
                return {
                    "success": True,
                    "message": f"USD asset created: {asset_name}",
                    "asset": asset_info
                }
            else:
                return {
                    "success": False,
                    "message": usd_result['error'],
                    "asset": None
                }
                
        except Exception as e:
            print(f"❌ DEBUG: Error processing mesh ZIP: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": f"Processing failed: {str(e)}",
                "asset": None
            }
    
    def _extract_and_validate_zip(self, zip_path: str, filename: str) -> Dict:
        """Extract ZIP and validate required files"""
        result = {
            "valid": False,
            "error": "",
            "files": {
                "obj_file": None,
                "mtl_file": None,
                "texture_files": [],
                "extract_dir": None
            }
        }
        
        try:
            # Create extraction directory
            extract_dir = os.path.join(self.temp_dir, f"extract_{int(time.time())}")
            os.makedirs(extract_dir, exist_ok=True)
            result["files"]["extract_dir"] = extract_dir
            
            # Extract ZIP
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # Find files
            for file_path in Path(extract_dir).rglob('*'):
                if file_path.is_file():
                    ext = file_path.suffix.lower()
                    
                    if ext == '.obj':
                        result["files"]["obj_file"] = str(file_path)
                    elif ext == '.mtl':
                        result["files"]["mtl_file"] = str(file_path)
                    elif ext in ['.jpg', '.jpeg', '.png', '.tiff', '.tga', '.bmp']:
                        result["files"]["texture_files"].append(str(file_path))
            
            # Validate required files
            if not result["files"]["obj_file"]:
                result["error"] = "No OBJ file found in ZIP"
                return result
            
            if not result["files"]["mtl_file"]:
                print("⚠️ DEBUG: No MTL file found, will create basic material")
            
            if not result["files"]["texture_files"]:
                print("⚠️ DEBUG: No texture files found, will use default material")
            
            result["valid"] = True
            print(f"✅ DEBUG: ZIP validated - OBJ: ✓, MTL: {bool(result['files']['mtl_file'])}, "
                  f"Textures: {len(result['files']['texture_files'])}")
            
            return result
            
        except Exception as e:
            result["error"] = f"ZIP extraction failed: {str(e)}"
            return result
    
    def _create_usd_asset(self, extracted: Dict, asset_name: str, filename: str, file_size: int) -> Dict:
        """Create USD file from extracted mesh data with proper texture handling"""
        try:
            # Create USD output path
            usd_dir = os.path.join(self.temp_dir, "usd_assets")
            os.makedirs(usd_dir, exist_ok=True)
            usd_path = os.path.join(usd_dir, f"{asset_name}.usd")
            
            print(f"🔧 DEBUG: Creating USD file: {usd_path}")
            print(f"📁 DEBUG: Available textures: {len(extracted['files']['texture_files'])}")
            for tex in extracted['files']['texture_files']:
                print(f"    - {Path(tex).name}")
            
            # Create USD stage
            stage = Usd.Stage.CreateNew(usd_path)
            
            # Set stage metadata
            stage.SetMetadata('metersPerUnit', 1.0)
            stage.SetMetadata('upAxis', 'Y')
            
            # Create root prim
            root_path = f"/{asset_name}"
            root_prim = stage.DefinePrim(root_path, "Xform")
            stage.SetDefaultPrim(root_prim)
            
            # Add metadata
            root_prim.SetMetadata('customData', {
                'source': 'roworks_mesh_zip',
                'original_filename': filename,
                'file_size': file_size,
                'created_by': 'roworks_ai_omniverse',
                'texture_count': len(extracted['files']['texture_files'])
            })
            
            # Import mesh with improved material handling
            mesh_success = self._import_obj_to_usd(
                stage,
                extracted['files']['obj_file'],
                extracted['files']['mtl_file'],
                extracted['files']['texture_files'],
                f"{root_path}/Mesh"
            )
            
            if not mesh_success:
                return {
                    "success": False,
                    "error": "Failed to import OBJ mesh to USD"
                }
            
            # Save USD file
            stage.Save()
            
            print(f"✅ DEBUG: USD asset created successfully: {usd_path}")
            
            # Verify textures are accessible
            self._verify_usd_textures(usd_path)
            
            return {
                "success": True,
                "usd_path": usd_path
            }
            
        except Exception as e:
            print(f"❌ DEBUG: Error creating USD asset: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": f"USD creation failed: {str(e)}"
            }
    
    def _import_obj_to_usd(self, stage, obj_path: str, mtl_path: Optional[str], 
                          texture_paths: List[str], mesh_prim_path: str) -> bool:
        """Import OBJ file with materials to USD with better texture handling"""
        try:
            print(f"🔧 DEBUG: Importing OBJ to USD: {Path(obj_path).name}")
            print(f"🎨 DEBUG: MTL file: {'✓' if mtl_path else '❌'}")
            print(f"🖼️ DEBUG: Textures: {len(texture_paths)} files")
            
            # Parse OBJ file
            vertices, faces, uvs, normals = self._parse_obj_file(obj_path)
            
            if not vertices or not faces:
                print("❌ DEBUG: No valid geometry found in OBJ file")
                return False
            
            # Create mesh prim
            mesh_prim = stage.DefinePrim(mesh_prim_path, "Mesh")
            mesh = UsdGeom.Mesh(mesh_prim)
            
            # Set mesh geometry
            mesh.CreatePointsAttr().Set(vertices)
            mesh.CreateFaceVertexIndicesAttr().Set(faces)
            mesh.CreateFaceVertexCountsAttr().Set([3] * (len(faces) // 3))  # Assuming triangles
            
            # Set UV coordinates if available - CRITICAL for textures
            uv_success = False
            if uvs:
                try:
                    primvars_api = UsdGeom.PrimvarsAPI(mesh_prim)
                    uv_primvar = primvars_api.CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray)
                    uv_primvar.Set(uvs)
                    uv_primvar.SetInterpolation(UsdGeom.Tokens.faceVarying)
                    uv_success = True
                    print("✅ DEBUG: UV coordinates set successfully")
                except Exception as e:
                    print(f"⚠️ DEBUG: Could not set UV coordinates: {e}")
                    # Try alternative method
                    try:
                        mesh.GetPrim().CreateAttribute("primvars:st", Sdf.ValueTypeNames.TexCoord2fArray).Set(uvs)
                        mesh.GetPrim().CreateAttribute("primvars:st:interpolation", Sdf.ValueTypeNames.Token).Set("faceVarying")
                        uv_success = True
                        print("✅ DEBUG: UV coordinates set via fallback method")
                    except Exception as e2:
                        print(f"⚠️ DEBUG: All UV methods failed: {e2}")
            
            # Set normals if available
            if normals:
                try:
                    mesh.CreateNormalsAttr().Set(normals)
                    mesh.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
                    print("✅ DEBUG: Normals set successfully")
                except Exception as e:
                    print(f"⚠️ DEBUG: Could not set normals: {e}")
            
            # Create and bind material - ONLY if we have textures and UVs
            material_created = False
            if texture_paths and uv_success:
                try:
                    material_success = self._create_usd_material(
                        stage, mtl_path, texture_paths, mesh_prim_path, mesh_prim
                    )
                    if material_success:
                        material_created = True
                        print("✅ DEBUG: Material with textures created successfully")
                    else:
                        print("⚠️ DEBUG: Material creation failed")
                except Exception as e:
                    print(f"⚠️ DEBUG: Material creation error: {e}")
            
            # Fallback: Create simple colored material
            if not material_created:
                try:
                    if texture_paths:
                        # We had textures but failed to apply them
                        mesh.CreateDisplayColorAttr().Set([(1.0, 0.8, 0.6)])  # Light orange to indicate issue
                        print("🟠 DEBUG: Applied orange color (texture issue)")
                    else:
                        # No textures available
                        mesh.CreateDisplayColorAttr().Set([(0.8, 0.8, 0.8)])  # Gray
                        print("⚫ DEBUG: Applied gray color (no textures)")
                except Exception as e:
                    print(f"⚠️ DEBUG: Could not set fallback color: {e}")
            
            print(f"✅ DEBUG: Mesh imported - {len(vertices)} vertices, {len(faces)//3} faces, "
                  f"UVs: {'✓' if uv_success else '❌'}, Material: {'✓' if material_created else '❌'}")
            return True
            
        except Exception as e:
            print(f"❌ DEBUG: Error importing OBJ to USD: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _parse_obj_file(self, obj_path: str) -> Tuple[List, List, List, List]:
        """Parse OBJ file and extract geometry data"""
        vertices = []
        faces = []
        uvs = []
        normals = []
        
        try:
            with open(obj_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('v '):  # Vertex
                        parts = line.split()[1:4]
                        if len(parts) >= 3:
                            vertices.append((float(parts[0]), float(parts[1]), float(parts[2])))
                    
                    elif line.startswith('vt '):  # Texture coordinate
                        parts = line.split()[1:3]
                        if len(parts) >= 2:
                            uvs.append((float(parts[0]), 1.0 - float(parts[1])))  # Flip V for USD
                    
                    elif line.startswith('vn '):  # Normal
                        parts = line.split()[1:4]
                        if len(parts) >= 3:
                            normals.append((float(parts[0]), float(parts[1]), float(parts[2])))
                    
                    elif line.startswith('f '):  # Face
                        parts = line.split()[1:]
                        face_indices = []
                        for part in parts:
                            # Handle different face formats (v, v/vt, v/vt/vn, v//vn)
                            indices = part.split('/')
                            vertex_idx = int(indices[0]) - 1  # Convert to 0-indexed
                            face_indices.append(vertex_idx)
                        
                        # Convert to triangles if needed
                        if len(face_indices) == 3:
                            faces.extend(face_indices)
                        elif len(face_indices) == 4:  # Quad -> two triangles
                            faces.extend([face_indices[0], face_indices[1], face_indices[2]])
                            faces.extend([face_indices[0], face_indices[2], face_indices[3]])
            
            print(f"🔧 DEBUG: Parsed OBJ - {len(vertices)} vertices, {len(faces)//3} triangles, "
                  f"{len(uvs)} UVs, {len(normals)} normals")
            
        except Exception as e:
            print(f"❌ DEBUG: Error parsing OBJ file: {e}")
        
        return vertices, faces, uvs, normals
    
    def _create_usd_material(self, stage, mtl_path: Optional[str], texture_paths: List[str],
                           mesh_prim_path: str, mesh_prim) -> bool:
        """Create USD material from MTL and textures with ABSOLUTE paths"""
        try:
            # Create material path
            material_name = f"{Path(mesh_prim_path).name}_Material"
            material_path = f"/Materials/{material_name}"
            
            print(f"🎨 DEBUG: Creating material: {material_path}")
            
            # Create material
            material_prim = stage.DefinePrim(material_path, "Material")
            material = UsdShade.Material(material_prim)
            
            # Create PBR shader
            shader_path = f"{material_path}/PreviewSurface"
            shader_prim = stage.DefinePrim(shader_path, "Shader")
            shader = UsdShade.Shader(shader_prim)
            shader.CreateIdAttr("UsdPreviewSurface")
            
            # Set default material properties
            shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.5)
            shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
            shader.CreateInput("specular", Sdf.ValueTypeNames.Float).Set(0.5)
            
            # Use first texture as diffuse if available
            if texture_paths:
                texture_path = texture_paths[0]
                
                # CRITICAL FIX: Convert to absolute path and copy texture to persistent location
                persistent_texture_path = self._copy_texture_to_persistent_location(texture_path, material_name)
                
                if persistent_texture_path:
                    print(f"🖼️ DEBUG: Using texture: {persistent_texture_path}")
                    
                    # Create texture shader
                    texture_shader_path = f"{material_path}/DiffuseTexture"
                    texture_prim = stage.DefinePrim(texture_shader_path, "Shader")
                    texture_shader = UsdShade.Shader(texture_prim)
                    texture_shader.CreateIdAttr("UsdUVTexture")
                    
                    # IMPORTANT: Use absolute path for texture
                    texture_shader.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(persistent_texture_path)
                    
                    # Create primvar reader for UV coordinates
                    primvar_path = f"{material_path}/PrimvarReader"
                    primvar_prim = stage.DefinePrim(primvar_path, "Shader")
                    primvar_shader = UsdShade.Shader(primvar_prim)
                    primvar_shader.CreateIdAttr("UsdPrimvarReader_float2")
                    primvar_shader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
                    
                    # Connect UV coordinates to texture
                    texture_shader.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
                        primvar_shader.ConnectableAPI(), "result"
                    )
                    
                    # Connect texture to material
                    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
                        texture_shader.ConnectableAPI(), "rgb"
                    )
                    
                    # Also try to set opacity if the texture has alpha
                    if texture_path.lower().endswith(('.png', '.tga')):
                        shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).ConnectToSource(
                            texture_shader.ConnectableAPI(), "a"
                        )
                    
                    print(f"✅ DEBUG: Created material with texture: {Path(persistent_texture_path).name}")
                else:
                    print("⚠️ DEBUG: Failed to copy texture, using default color")
                    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set((0.7, 0.7, 0.7))
            else:
                # Default color when no textures
                shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set((0.8, 0.8, 0.8))
                print("✅ DEBUG: Created material with default color")
            
            # Create material output
            material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
            
            # Bind material to mesh
            binding_api = UsdShade.MaterialBindingAPI(mesh_prim)
            binding_api.Bind(material)
            
            print("✅ DEBUG: Material bound to mesh successfully")
            return True
            
        except Exception as e:
            print(f"❌ DEBUG: Error creating USD material: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _copy_texture_to_persistent_location(self, source_texture_path: str, material_name: str) -> Optional[str]:
        """Copy texture to persistent location and return absolute path"""
        try:
            if not os.path.exists(source_texture_path):
                print(f"⚠️ DEBUG: Source texture not found: {source_texture_path}")
                return None
            
            # Create persistent textures directory
            textures_dir = os.path.join(self.temp_dir, "textures")
            os.makedirs(textures_dir, exist_ok=True)
            
            # Generate unique filename
            source_name = Path(source_texture_path).name
            safe_material_name = re.sub(r'[^a-zA-Z0-9_]', '_', material_name)
            dest_filename = f"{safe_material_name}_{source_name}"
            dest_path = os.path.join(textures_dir, dest_filename)
            
            # Copy texture file
            shutil.copy2(source_texture_path, dest_path)
            
            # Return absolute path
            absolute_path = os.path.abspath(dest_path)
            print(f"📁 DEBUG: Texture copied to: {absolute_path}")
            
            return absolute_path
            
        except Exception as e:
            print(f"❌ DEBUG: Error copying texture: {e}")
            return None
    
    def _verify_usd_textures(self, usd_path: str):
        """Verify that textures in USD file are accessible"""
        try:
            stage = Usd.Stage.Open(usd_path)
            if not stage:
                print("⚠️ DEBUG: Cannot open USD stage for texture verification")
                return
            
            texture_count = 0
            missing_textures = []
            
            for prim in stage.Traverse():
                if prim.IsA(UsdShade.Shader):
                    shader = UsdShade.Shader(prim)
                    
                    # Look for file inputs (textures)
                    for input_name in shader.GetInputNames():
                        input_attr = shader.GetInput(input_name)
                        if input_attr.GetTypeName() == Sdf.ValueTypeNames.Asset:
                            asset_path = input_attr.Get()
                            if asset_path:
                                texture_path = str(asset_path.resolvedPath) or str(asset_path)
                                texture_count += 1
                                
                                if not os.path.exists(texture_path):
                                    missing_textures.append(texture_path)
                                    print(f"❌ DEBUG: Missing texture: {texture_path}")
                                else:
                                    print(f"✅ DEBUG: Found texture: {texture_path}")
            
            print(f"📊 DEBUG: Texture verification - {texture_count} total, {len(missing_textures)} missing")
            
        except Exception as e:
            print(f"⚠️ DEBUG: Error verifying textures: {e}")
    
    def _schedule_usd_import(self, usd_path: str, asset_name: str):
        """Schedule USD asset import using non-blocking importer"""
        print(f"🔧 DEBUG: Scheduling USD import: {asset_name}")
        
        def import_callback(success: bool, name: str, message: str):
            """Callback when import completes"""
            print(f"🔧 DEBUG: Import callback - {name}: {success} - {message}")
            
            # Update asset status
            for asset in self.uploaded_assets:
                if asset["asset_name"] == name:
                    asset["imported_to_scene"] = success
                    asset["scene_prim_path"] = f"/World/RoWorks/Assets/{name}" if success else None
                    asset["import_message"] = message
                    asset["import_status"] = "completed" if success else "failed"
                    break
            
            if success:
                print(f"✅ DEBUG: Asset imported successfully: {name}")
            else:
                print(f"❌ DEBUG: Asset import failed: {name} - {message}")
        
        # Use the non-blocking importer
        import_task = self.usd_importer.schedule_import(usd_path, asset_name, import_callback)
        
        if import_task:
            # Mark as importing
            for asset in self.uploaded_assets:
                if asset["asset_name"] == asset_name:
                    asset["import_status"] = "importing"
                    asset["import_message"] = "Import in progress..."
                    break
            print(f"✅ DEBUG: Import scheduled successfully: {asset_name}")
        else:
            # Mark as failed
            for asset in self.uploaded_assets:
                if asset["asset_name"] == asset_name:
                    asset["import_status"] = "failed"
                    asset["import_message"] = "Failed to schedule import"
                    break
            print(f"❌ DEBUG: Import scheduling failed: {asset_name}")
    
    def _sanitize_name(self, filename: str) -> str:
        """Create safe USD prim name"""
        # Remove extension and sanitize
        name = Path(filename).stem
        name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        if name and name[0].isdigit():
            name = f"Asset_{name}"
        return name or "UnnamedAsset"
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status"""
        base_status = {
            "total_assets": len(self.uploaded_assets),
            "workflow": "Upload mesh ZIP (OBJ+MTL+textures) to create USD assets",
            "temp_dir": self.temp_dir,
            "scene_manager_available": self.scene_manager is not None
        }
        
        # Add import queue status
        importer_status = self.usd_importer.get_status()
        base_status.update({
            "import_queue_length": importer_status["queue_length"],
            "currently_importing": importer_status["is_importing"],
            "queued_imports": importer_status["queued_imports"]
        })
        
        return base_status
    
    def get_assets(self) -> List[Dict]:
        """Get all uploaded assets"""
        return self.uploaded_assets
    
    def get_scene_objects(self) -> List[Dict]:
        """Get all scene objects from scene manager or internal tracking"""
        scene_objects = []
        
        # Try to get from scene manager first
        if self.scene_manager:
            try:
                scene_stats = self.scene_manager.get_scene_stats()
                scene_objects = scene_stats.get("objects", [])
                print(f"🔧 DEBUG: Retrieved {len(scene_objects)} objects from scene manager")
            except Exception as e:
                print(f"⚠️ DEBUG: Error getting objects from scene manager: {e}")
        
        # Add our uploaded assets to the list
        for asset in self.uploaded_assets:
            if asset.get("imported_to_scene", False):
                scene_objects.append({
                    "name": asset["asset_name"],
                    "type": "mesh_asset",
                    "prim_path": asset.get("scene_prim_path", f"/World/RoWorks/Assets/{asset['asset_name']}"),
                    "usd_path": asset["usd_path"],
                    "imported": True,
                    "file_size": asset["file_size"],
                    "created_at": asset["created_at"],
                    "import_status": asset.get("import_status", "unknown")
                })
        
        return scene_objects


class MeshAPIService:
    """API service for mesh ZIP to USD conversion with all fixes"""
    
    def __init__(self):
        print("🔧 DEBUG: Initializing MeshAPIService")
        if not FASTAPI_AVAILABLE:
            print("❌ DEBUG: FastAPI not available, API service disabled")
            self._app = None
            self._server = None
            self._server_thread = None
            self.usd_manager = MeshUSDManager()
            return
            
        self._app = FastAPI(
            title="RoWorks Mesh USD API",
            description="Mesh ZIP (OBJ+MTL+textures) to USD conversion with texture fixes",
            version="2.1.0"
        )
        
        # Enable CORS with proper headers
        self._app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        self._server = None
        self._server_thread = None
        self._startup_time = time.time()
        self.usd_manager = MeshUSDManager()
        self._setup_routes()
        print("🔧 DEBUG: Mesh API Service initialized with CORS enabled")
    
    def _setup_routes(self):
        """Setup API routes with all endpoints"""
        if not self._app:
            return
            
        @self._app.get("/health")
        async def health_check():
            return {
                "status": "healthy",
                "service": "mesh_usd_creation",
                "version": "2.1.0",
                "workflow": "Upload mesh ZIP (OBJ+MTL+textures) to create USD assets",
                "cors_enabled": True,
                "endpoints_available": [
                    "/health", "/status", "/mesh/import", "/debug/analyze-zip", 
                    "/debug/import-status", "/assets", "/assets/clear", "/formats/supported"
                ],
                **self.usd_manager.get_status()
            }
        
        @self._app.get("/status")
        async def get_enhanced_status():
            base_status = self.usd_manager.get_status()
            
            return {
                **base_status,
                "api_version": "2.1.0",
                "service_type": "mesh_processing",
                "cors_enabled": True,
                "features": [
                    "mesh_zip_upload",
                    "usd_creation", 
                    "non_blocking_import",
                    "texture_processing",
                    "material_binding",
                    "absolute_texture_paths"
                ],
                "uptime_info": {
                    "startup_time": self._startup_time,
                    "current_time": time.time(),
                    "uptime_seconds": time.time() - self._startup_time
                }
            }
        
        @self._app.get("/assets")
        async def get_assets():
            return {
                "assets": self.usd_manager.get_assets(),
                "scene_objects": self.usd_manager.get_scene_objects()
            }
        
        @self._app.get("/scene/info")
        async def get_scene_info():
            """Get scene information - enhanced version"""
            scene_objects = self.usd_manager.get_scene_objects()
            
            # Count objects by type for compatibility
            by_type = {}
            by_status = {}
            
            for obj in scene_objects:
                obj_type = obj.get("type", "unknown")
                by_type[obj_type] = by_type.get(obj_type, 0) + 1
                
                status = "imported" if obj.get("imported", False) else "pending"
                by_status[status] = by_status.get(status, 0) + 1
            
            return {
                "total_objects": len(scene_objects),
                "objects_by_type": by_type,
                "objects_by_status": by_status,
                "objects": scene_objects,
                "workflow": "Mesh ZIP (OBJ+MTL+textures) to USD assets",
                "last_updated": time.time()
            }
        
        @self._app.get("/debug/import-status")
        async def get_detailed_import_status():
            """Get detailed import status - matches what web server expects"""
            return {
                "import_system": "simplified_non_blocking_v2",
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
                "queue_info": {
                    "length": len(self.usd_manager.usd_importer.import_queue),
                    "is_importing": self.usd_manager.usd_importer.is_importing,
                    "queued_items": [task["asset_name"] for task in self.usd_manager.usd_importer.import_queue]
                }
            }
        
        @self._app.get("/formats/supported")
        async def get_supported_formats():
            """Get supported file formats"""
            return {
                "input_format": ".zip",
                "required_contents": ["*.obj", "*.mtl (optional)", "*.jpg/*.png (optional)"],
                "description": "ZIP archives containing OBJ mesh with optional MTL materials and texture images",
                "max_file_size": "100MB",
                "workflow": "Upload mesh ZIP → USD asset creation → Scene import",
                "supported_extensions": {
                    "mesh": [".obj"],
                    "materials": [".mtl"],
                    "textures": [".jpg", ".jpeg", ".png", ".tiff", ".tga", ".bmp"]
                },
                "texture_features": [
                    "Absolute path resolution",
                    "Persistent texture storage",
                    "UV coordinate mapping",
                    "PBR material creation"
                ]
            }
        
        @self._app.post("/debug/test-connectivity")
        async def test_connectivity():
            """Test endpoint for web server connectivity"""
            return {
                "success": True,
                "message": "RoWorks API is responding",
                "service": "roworks_mesh_usd_api",
                "version": "2.1.0",
                "timestamp": time.time(),
                "endpoints": {
                    "health": "/health",
                    "status": "/status", 
                    "mesh_import": "/mesh/import",
                    "analyze_zip": "/debug/analyze-zip",
                    "import_status": "/debug/import-status",
                    "assets": "/assets",
                    "clear_scene": "/assets/clear",
                    "supported_formats": "/formats/supported"
                }
            }
        
        @self._app.post("/mesh/import")
        async def import_mesh(file: UploadFile = File(...)):
            """Import mesh ZIP file containing OBJ, MTL, and textures"""
            print(f"🔧 DEBUG: Uploading mesh ZIP: {file.filename}")
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
                
                # Size limit
                max_size = 100 * 1024 * 1024  # 100MB
                if file_size > max_size:
                    raise HTTPException(
                        status_code=400,
                        detail=f"File too large. Maximum size: {max_size // 1024 // 1024}MB"
                    )
                
                # Save ZIP file
                zip_path = os.path.join(self.usd_manager.temp_dir, file.filename)
                with open(zip_path, 'wb') as f:
                    f.write(content)
                
                # Process ZIP and create USD
                result = self.usd_manager.process_mesh_zip(zip_path, file.filename, file_size)
                
                elapsed_time = time.time() - start_time
                print(f"🔧 DEBUG: Mesh processing completed in {elapsed_time:.2f}s")
                
                if result["success"]:
                    return {
                        "success": True,
                        "message": result["message"],
                        "data": {
                            **result["asset"],
                            "processing_time": elapsed_time
                        }
                    }
                else:
                    raise HTTPException(status_code=400, detail=result["message"])
                    
            except HTTPException:
                raise
            except Exception as e:
                elapsed_time = time.time() - start_time
                print(f"❌ DEBUG: Mesh import error after {elapsed_time:.2f}s: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self._app.post("/debug/analyze-zip")
        async def analyze_zip(file: UploadFile = File(...)):
            """Debug endpoint to analyze ZIP contents without creating USD"""
            try:
                if not file.filename or not file.filename.lower().endswith('.zip'):
                    raise HTTPException(status_code=400, detail="File must be a ZIP archive")
                
                # Save temporary file
                content = await file.read()
                temp_path = os.path.join(self.usd_manager.temp_dir, f"analyze_{file.filename}")
                
                with open(temp_path, 'wb') as f:
                    f.write(content)
                
                # Analyze contents
                extracted = self.usd_manager._extract_and_validate_zip(temp_path, file.filename)
                
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
                
                return {
                    "success": True,
                    "message": "ZIP analysis complete",
                    "analysis": analysis
                }
                
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Analysis failed: {str(e)}"
                }
        
        @self._app.post("/debug/force-import/{asset_name}")
        async def force_import_asset(asset_name: str):
            """Force retry import of a specific asset"""
            try:
                # Find the asset
                target_asset = None
                for asset in self.usd_manager.uploaded_assets:
                    if asset["asset_name"] == asset_name:
                        target_asset = asset
                        break
                
                if not target_asset:
                    raise HTTPException(status_code=404, detail="Asset not found")
                
                if not target_asset.get("usd_path") or not os.path.exists(target_asset["usd_path"]):
                    raise HTTPException(status_code=400, detail="USD file not found")
                
                # Schedule import
                self.usd_manager._schedule_usd_import(target_asset["usd_path"], asset_name)
                
                return {
                    "success": True,
                    "message": f"Import scheduled for {asset_name}",
                    "asset": target_asset
                }
                
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self._app.delete("/assets/clear")
        async def clear_assets():
            """Clear all assets and scene objects"""
            self.usd_manager.uploaded_assets.clear()
            
            # Also clear from scene manager if available
            if self.usd_manager.scene_manager:
                try:
                    await self.usd_manager.scene_manager.clear_scene()
                    print("✅ DEBUG: Scene cleared via scene manager")
                except Exception as e:
                    print(f"⚠️ DEBUG: Error clearing scene via scene manager: {e}")
            
            return {"success": True, "message": "All assets and scene objects cleared"}
    
    def start_server(self):
        """Start the API server"""
        if not self._app:
            print("❌ DEBUG: Cannot start server - FastAPI not available")
            return
            
        def run_server():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                config = uvicorn.Config(
                    app=self._app,
                    host="0.0.0.0",
                    port=49101,
                    log_level="error",  # Reduced log level
                    access_log=False
                )
                
                self._server = uvicorn.Server(config)
                print("🚀 DEBUG: Mesh USD API server starting on port 49101")
                
                loop.run_until_complete(self._server.serve())
                
            except Exception as e:
                print(f"❌ DEBUG: Server error: {e}")
                import traceback
                traceback.print_exc()
        
        try:
            self._server_thread = threading.Thread(target=run_server, daemon=True)
            self._server_thread.start()
        except Exception as e:
            print(f"❌ DEBUG: Error starting server thread: {e}")
    
    def stop_server(self):
        if self._server:
            self._server.should_exit = True


class RoWorksServiceApiExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        print("🚀 DEBUG: RoWorks Complete Mesh USD API Extension Starting!")
        
        try:
            self._api_service = MeshAPIService()
            
            if FASTAPI_AVAILABLE:
                self._api_service.start_server()
                print("✅ DEBUG: Complete Mesh USD extension startup complete")
                print(f"🚀 API: http://localhost:49101 (Complete Mesh USD Creation)")
                print("📝 Upload mesh ZIP files (OBJ+MTL+textures) to create USD assets")
                print("🎨 Supports textured 3D models with absolute texture paths")
                print("📊 Max file size: 100MB")
                print("🔄 Non-blocking USD import prevents UI hanging")
                print("🌐 CORS enabled for web interface integration")
                print("🖼️ Fixed texture path resolution for materials")
                
                # Print available endpoints for debugging
                print("🔗 Available API endpoints:")
                endpoints = [
                    "GET  /health - Health check with full status",
                    "GET  /status - Enhanced service status", 
                    "POST /mesh/import - Upload mesh ZIP with texture fixes",
                    "POST /debug/analyze-zip - Analyze ZIP contents",
                    "GET  /debug/import-status - Detailed import queue status",
                    "POST /debug/force-import/{name} - Force retry import",
                    "GET  /assets - List scene assets",
                    "GET  /scene/info - Enhanced scene information",
                    "DELETE /assets/clear - Clear scene",
                    "GET  /formats/supported - Supported formats with features",
                    "POST /debug/test-connectivity - Connection test"
                ]
                for endpoint in endpoints:
                    print(f"     {endpoint}")
                
                print("🎯 Key Features:")
                print("     ✅ Absolute texture paths for materials")
                print("     ✅ Persistent texture storage")
                print("     ✅ Non-blocking USD import queue")
                print("     ✅ Enhanced CORS support")
                print("     ✅ Real-time import status tracking")
                print("     ✅ Comprehensive error handling")
                    
            else:
                print("⚠️ DEBUG: API service disabled - FastAPI dependencies not available")
                print("🔧 DEBUG: Extension will continue without API functionality")
            
        except Exception as e:
            print(f"❌ DEBUG: Extension startup failed: {e}")
            import traceback
            traceback.print_exc()
        
    def on_shutdown(self):
        print("🔧 DEBUG: Complete Mesh USD extension shutting down")
        
        if hasattr(self, '_api_service') and self._api_service:
            self._api_service.stop_server()


# Public API functions for compatibility
def some_public_function(x):
    """Legacy function for compatibility"""
    return x * x * x * x
