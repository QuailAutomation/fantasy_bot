"""Configuration for app."""
import os
import logging

from enum import Enum

class CacheBacking(Enum):
    file = "file" # S_PS7 or S_PSR
    redis= "redis"

LOG_LEVEL=os.getenv("LOG_LEVEL", 'INFO')
ENV = os.getenv("FLASK_ENV")
DEBUG = ENV == "development"
CELERY_TIMEZONE = 'US/Pacific'
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL",default='amqp://guest:guest@localhost:5672')
# celery_result_backend = os.getenv("CELERY_RESULT_BACKEND_URL")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND",default='redis://127.0.0.1:6379/0')
CELERY_RESULT_EXPIRES = 60

CELERYD_PREFETCH_MULTIPLIER=3
CELERY_PREFETCH_MULTIPLIER=3

CELERY_WORKER_SEND_TASK_EVENTS = True
    
CELERY_IMPORTS = ('csh_fantasy_bot.tasks')
CELERYBEAT_SCHEDULE = {
        # 'refresh': {
        #     'task': 'refresh',
        #     'schedule': 60
        # },
            'check_roster_moves': {
            'task': 'check_roster_moves',
            'schedule': 300
        },
    }

CELERY_TASK_FILE_WRITE_PATH = "/Users/craigh/dev/fantasy_bot"

ELASTIC_URL = os.getenv("FB_ELASTIC_URL", default="http://localhost:9200")
logging.getLogger().info(f"ELASTIC_URL is: {ELASTIC_URL}")
GELF_URL = os.getenv("GELF_URL", default=None)

CACHE_BACKING = CacheBacking[os.getenv("FB_CACHE_BACKING", default=CacheBacking.file.value)]
OAUTH_TOKEN_BACKING = CacheBacking[os.getenv("FB_OAUTH_TOKEN_BACKING", default=CacheBacking.file.value)]
