import omni.ext
import logging

logger = logging.getLogger(__name__)

# Global variable to store scene manager (simple approach)
_global_scene_manager = None

class RoWorksSceneManager:
    def __init__(self):
        self._scene_objects = {}
        logger.info("RoWorks Scene Manager initialized")
    
    def get_scene_objects(self):
        return self._scene_objects
    
    def get_scene_object(self, prim_path: str):
        return self._scene_objects.get(prim_path)
    
    async def clear_scene(self):
        self._scene_objects.clear()
        logger.info("Scene cleared")

class RoWorksSceneManagerExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        global _global_scene_manager
        logger.info("[roworks.scene.manager] Starting up")
        print("🚀 RoWorks Scene Manager Extension Started!")
        
        self._scene_manager = RoWorksSceneManager()
        _global_scene_manager = self._scene_manager
        
    def on_shutdown(self):
        global _global_scene_manager
        logger.info("[roworks.scene.manager] Shutting down")
        _global_scene_manager = None

def get_scene_manager():
    """Get the global scene manager instance"""
    return _global_scene_manager
