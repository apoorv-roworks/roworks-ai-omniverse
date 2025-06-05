import omni.ext
import logging

logger = logging.getLogger(__name__)

class RoWorksVisualizationExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        logger.info("[roworks.visualization] Starting up")
        print("🚀 RoWorks Visualization Extension Started!")
        
    def on_shutdown(self):
        logger.info("[roworks.visualization] Shutting down")
