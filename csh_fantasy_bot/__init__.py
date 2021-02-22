import os
import logging
import redis

from selenium.webdriver.remote.remote_connection import LOGGER as serverLogger
serverLogger.setLevel(logging.WARNING)
logging.getLogger("yahoo_oauth").setLevel(level=logging.INFO)



class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class RedisClient(redis.Redis, metaclass=Singleton):
    def __init__(self) -> None:
        redis_url = os.getenv("REDIS_URL",default='localhost')
        self.pool = redis.ConnectionPool(host = redis_url)

    @property
    def conn(self):
        if not hasattr(self, '_conn'):
            self.getConnection()
        return self._conn

    def getConnection(self):
        self._conn = redis.Redis(connection_pool = self.pool)
    
    
