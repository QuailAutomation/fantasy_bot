
import os
import logging

LOG_LEVEL=os.getenv("LOG_LEVEL", 'INFO')
logging.basicConfig(level=LOG_LEVEL)
logging.getLogger().setLevel(LOG_LEVEL)
LOG = logging.getLogger(__name__)

# reduce log levels for selenium.  debug is chatty, doesnt default to root level
from selenium.webdriver.remote.remote_connection import LOGGER as serverLogger
serverLogger.setLevel(logging.WARNING)
logging.getLogger("yahoo_oauth").setLevel(level=logging.INFO)

def print_logger_heirarchy(log):
    print(f'{log.name}, effective_level: {log.getEffectiveLevel()}, Type: {type(log)}')
    if log.parent: print_logger_heirarchy(log.parent)

    
    
