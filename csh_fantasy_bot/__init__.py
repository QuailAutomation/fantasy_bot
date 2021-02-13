import logging

from selenium.webdriver.remote.remote_connection import LOGGER as serverLogger
serverLogger.setLevel(logging.WARNING)
logging.getLogger("yahoo_oauth").setLevel(level=logging.INFO)