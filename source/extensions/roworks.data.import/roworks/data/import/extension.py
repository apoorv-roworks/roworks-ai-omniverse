import omni.ext
import logging

logger = logging.getLogger(__name__)

class RoWorksDataImportExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        logger.info("[roworks.data.import] Starting up")
        print("🚀 RoWorks Data Import Extension Started!")
        
    def on_shutdown(self):
        logger.info("[roworks.data.import] Shutting down")
