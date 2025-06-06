import zipfile
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Tuple, Dict, List
import logging

# USD and Omniverse imports
from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf
import omni.usd
import omni.kit.commands

logger = logging.getLogger(__name__)

class PolycamProcessor:
    """Handles Polycam ZIP files containing OBJ, MTL, and texture files"""
    
    def __init__(self):
        self.temp_dirs = []
    
    def extract_polycam_zip(self, zip_path: str) -> Tuple[bool, str, Dict]:
        """
        Extract Polycam ZIP file and organize contents
        
        Returns:
            (success, message, extracted_files_dict)
        """
        try:
            # Create temporary directory
            temp_dir = tempfile.mkdtemp(prefix="polycam_")
            self.temp_dirs.append(temp_dir)
            
            extracted_files = {
                'obj_file': None,
                'mtl_file': None,
                'texture_files': [],
                'xyz_file': None,
                'temp_dir': temp_dir
            }
            
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
                    elif ext == '.xyz':
                        extracted_files['xyz_file'] = str(file_path)
                    elif ext in ['.jpg', '.jpeg', '.png', '.tiff', '.tga', '.bmp']:
                        extracted_files['texture_files'].append(str(file_path))
            
            # Validate required files
            if not extracted_files['obj_file']:
                return False, "No OBJ file found in ZIP", {}
            
            logger.info(f"Extracted Polycam files: OBJ={bool(extracted_files['obj_file'])}, "
                       f"MTL={bool(extracted_files['mtl_file'])}, "
                       f"Textures={len(extracted_files['texture_files'])}, "
                       f"XYZ={bool(extracted_files['xyz_file'])}")
            
            return True, "Successfully extracted Polycam files", extracted_files
            
        except Exception as e:
            logger.error(f"Error extracting Polycam ZIP: {e}")
            return False, f"Extraction failed: {str(e)}", {}
    
    def create_usd_from_polycam(self, extracted_files: Dict, output_path: str, asset_name: str) -> Tuple[bool, str]:
        """
        Create USD file from extracted Polycam files
        
        Args:
            extracted_files: Dictionary from extract_polycam_zip
            output_path: Path where to save the USD file
            asset_name: Name for the asset
        """
        try:
            # Create USD stage
            stage = Usd.Stage.CreateNew(output_path)
            
            # Set up stage metadata
            stage.SetMetadata('metersPerUnit', 1.0)
            stage.SetMetadata('upAxis', 'Y')
            
            # Create root prim
            root_prim = stage.DefinePrim(f"/{asset_name}", "Xform")
            stage.SetDefaultPrim(root_prim)
            
            # Import mesh with materials
            mesh_success = self._import_mesh_to_usd(
                stage, 
                extracted_files['obj_file'], 
                extracted_files.get('mtl_file'),
                extracted_files.get('texture_files', []),
                f"/{asset_name}/Mesh"
            )
            
            # Import point cloud if available
            if extracted_files.get('xyz_file'):
                pc_success = self._import_pointcloud_to_usd(
                    stage,
                    extracted_files['xyz_file'],
                    f"/{asset_name}/PointCloud"
                )
            
            # Add metadata
            root_prim.SetMetadata('customData', {
                'source': 'polycam',
                'original_files': {
                    'obj': Path(extracted_files['obj_file']).name if extracted_files['obj_file'] else None,
                    'mtl': Path(extracted_files['mtl_file']).name if extracted_files['mtl_file'] else None,
                    'xyz': Path(extracted_files['xyz_file']).name if extracted_files['xyz_file'] else None,
                    'textures': [Path(f).name for f in extracted_files.get('texture_files', [])]
                }
            })
            
            # Save stage
            stage.Save()
            
            logger.info(f"Successfully created USD file: {output_path}")
            return True, f"USD file created: {output_path}"
            
        except Exception as e:
            logger.error(f"Error creating USD from Polycam: {e}")
            return False, f"USD creation failed: {str(e)}"
    
    def _import_mesh_to_usd(self, stage, obj_path: str, mtl_path: Optional[str], 
                           texture_paths: List[str], mesh_prim_path: str) -> bool:
        """Import OBJ mesh with materials to USD"""
        try:
            # Create mesh prim
            mesh_prim = stage.DefinePrim(mesh_prim_path, "Mesh")
            mesh = UsdGeom.Mesh(mesh_prim)
            
            # Parse OBJ file
            vertices, faces, uvs, normals = self._parse_obj_file(obj_path)
            
            # Set mesh data
            mesh.CreatePointsAttr().Set(vertices)
            mesh.CreateFaceVertexIndicesAttr().Set(faces)
            mesh.CreateFaceVertexCountsAttr().Set([len(face) for face in self._group_faces(faces)])
            
            if uvs:
                mesh.CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray).Set(uvs)
            
            if normals:
                mesh.CreateNormalsAttr().Set(normals)
                mesh.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
            
            # Create material if MTL file exists
            if mtl_path and texture_paths:
                self._create_material(stage, mtl_path, texture_paths, mesh_prim_path + "_material", mesh_prim)
            
            return True
            
        except Exception as e:
            logger.error(f"Error importing mesh to USD: {e}")
            return False
    
    def _import_pointcloud_to_usd(self, stage, xyz_path: str, pc_prim_path: str) -> bool:
        """Import XYZ point cloud to USD"""
        try:
            # Read XYZ file
            points = []
            colors = []
            
            with open(xyz_path, 'r') as f:
                for line_num, line in enumerate(f):
                    if line_num > 100000:  # Limit for performance
                        break
                    
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        try:
                            x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                            points.append((x, y, z))
                            
                            # If RGB values are present
                            if len(parts) >= 6:
                                r, g, b = float(parts[3]), float(parts[4]), float(parts[5])
                                # Normalize if values are in 0-255 range
                                if r > 1.0 or g > 1.0 or b > 1.0:
                                    r, g, b = r/255.0, g/255.0, b/255.0
                                colors.append((r, g, b))
                            else:
                                colors.append((1.0, 1.0, 1.0))  # Default white
                                
                        except ValueError:
                            continue
            
            if not points:
                return False
            
            # Create points prim
            points_prim = stage.DefinePrim(pc_prim_path, "Points")
            points_geom = UsdGeom.Points(points_prim)
            
            # Set point data
            points_geom.CreatePointsAttr().Set(points)
            points_geom.CreateWidthsAttr().Set([1.0] * len(points))
            
            if colors:
                points_geom.CreateDisplayColorAttr().Set(colors)
            
            logger.info(f"Imported {len(points)} points to USD")
            return True
            
        except Exception as e:
            logger.error(f"Error importing point cloud to USD: {e}")
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
                        vertices.append((float(parts[0]), float(parts[1]), float(parts[2])))
                    
                    elif line.startswith('vt '):  # Texture coordinate
                        parts = line.split()[1:3]
                        uvs.append((float(parts[0]), float(parts[1])))
                    
                    elif line.startswith('vn '):  # Normal
                        parts = line.split()[1:4]
                        normals.append((float(parts[0]), float(parts[1]), float(parts[2])))
                    
                    elif line.startswith('f '):  # Face
                        face_vertices = []
                        parts = line.split()[1:]
                        for part in parts:
                            # Handle different face formats (v, v/vt, v/vt/vn, v//vn)
                            indices = part.split('/')
                            vertex_idx = int(indices[0]) - 1  # OBJ is 1-indexed
                            face_vertices.append(vertex_idx)
                        faces.extend(face_vertices)
            
        except Exception as e:
            logger.error(f"Error parsing OBJ file: {e}")
        
        return vertices, faces, uvs, normals
    
    def _group_faces(self, face_indices: List[int]) -> List[List[int]]:
        """Group face indices into individual faces"""
        # Simple triangulation - assumes triangular faces
        faces = []
        for i in range(0, len(face_indices), 3):
            if i + 2 < len(face_indices):
                faces.append([face_indices[i], face_indices[i+1], face_indices[i+2]])
        return faces
    
    def _create_material(self, stage, mtl_path: str, texture_paths: List[str], 
                        material_name: str, mesh_prim) -> bool:
        """Create USD material from MTL file"""
        try:
            # Create material
            material_path = f"/Materials/{material_name}"
            material_prim = stage.DefinePrim(material_path, "Material")
            material = UsdShade.Material(material_prim)
            
            # Create shader
            shader_prim = stage.DefinePrim(f"{material_path}/Shader", "Shader")
            shader = UsdShade.Shader(shader_prim)
            shader.CreateIdAttr("UsdPreviewSurface")
            
            # Set basic material properties
            shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.4)
            shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
            
            # If texture files exist, use the first one as diffuse
            if texture_paths:
                texture_path = texture_paths[0]
                
                # Create texture reader
                texture_prim = stage.DefinePrim(f"{material_path}/DiffuseTexture", "Shader")
                texture_shader = UsdShade.Shader(texture_prim)
                texture_shader.CreateIdAttr("UsdUVTexture")
                texture_shader.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(texture_path)
                
                # Connect texture to shader
                shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
                    texture_shader.ConnectableAPI(), "rgb"
                )
                
                # Create texture coordinate reader
                st_reader_prim = stage.DefinePrim(f"{material_path}/STReader", "Shader")
                st_reader = UsdShade.Shader(st_reader_prim)
                st_reader.CreateIdAttr("UsdPrimvarReader_float2")
                st_reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
                
                # Connect ST reader to texture
                texture_shader.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
                    st_reader.ConnectableAPI(), "result"
                )
            
            # Create material output
            material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
            
            # Bind material to mesh
            UsdShade.MaterialBindingAPI(mesh_prim).Bind(material)
            
            return True
            
        except Exception as e:
            logger.error(f"Error creating material: {e}")
            return False
    
    def cleanup(self):
        """Clean up temporary directories"""
        for temp_dir in self.temp_dirs:
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Could not clean up temp dir {temp_dir}: {e}")
        self.temp_dirs.clear()


class EnhancedPolycamImporter:
    """Enhanced importer for Polycam files that creates USD assets"""
    
    def __init__(self, scene_manager):
        self.scene_manager = scene_manager
        self.processor = PolycamProcessor()
    
    def import_polycam_zip(self, zip_path: str, asset_name: str = None) -> Tuple[bool, str, Dict]:
        """
        Import Polycam ZIP file and create USD asset
        
        Args:
            zip_path: Path to the Polycam ZIP file
            asset_name: Name for the asset (optional)
        
        Returns:
            (success, message, asset_data)
        """
        try:
            if not asset_name:
                asset_name = Path(zip_path).stem
            
            # Extract ZIP contents
            success, message, extracted_files = self.processor.extract_polycam_zip(zip_path)
            if not success:
                return False, message, {}
            
            # Create USD file
            output_dir = Path(tempfile.gettempdir()) / "roworks_usd_assets"
            output_dir.mkdir(exist_ok=True)
            usd_path = output_dir / f"{asset_name}.usd"
            
            success, message = self.processor.create_usd_from_polycam(
                extracted_files, str(usd_path), asset_name
            )
            
            if not success:
                return False, message, {}
            
            # Import USD into scene
            scene_object = self.scene_manager.import_usd_asset(str(usd_path), asset_name)
            
            if scene_object:
                asset_data = {
                    "name": asset_name,
                    "usd_path": str(usd_path),
                    "source": "polycam",
                    "extracted_files": extracted_files,
                    "scene_object": scene_object.to_dict()
                }
                
                return True, f"Successfully imported Polycam asset: {asset_name}", asset_data
            else:
                return False, "Failed to import USD into scene", {}
                
        except Exception as e:
            logger.error(f"Error importing Polycam ZIP: {e}")
            return False, f"Import failed: {str(e)}", {}
        finally:
            # Cleanup temporary files
            self.processor.cleanup()
