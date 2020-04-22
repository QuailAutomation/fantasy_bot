"""Configuration for app."""
import os
import logging

log = logging.getLogger(__name__)


ENV = os.getenv("FLASK_ENV")
DEBUG = ENV == "development"
CELERY_TIMEZONE = 'US/Pacific'
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL",default='amqp://guest:guest@localhost:5672')
# celery_result_backend = os.getenv("CELERY_RESULT_BACKEND_URL")
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

ELASTIC_URL = os.getenv("ELASTIC_URL", default="http://localhost:9200")
GELF_URL = os.getenv("GELF_URL", default="192.168.1.20")