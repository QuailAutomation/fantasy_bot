"""Config for Celery."""
from celery.schedules import crontab


# CELERY_IMPORTS = ('csh_fantasy_bot.tasks')
class Config(object):
    CELERY_TASK_RESULT_EXPIRES = 30
    CELERY_TIMEZONE = 'US/Pacific'
    BROKER_URL = 'amqp://guest:guest@localhost:5672'
    celery_result_backend = 'redis://127.0.0.1:6379/0'
    result_backend = 'redis://127.0.0.1:6379/0'
    CELERY_RESULT_BACKEND = 'redis://127.0.0.1:6379/0'
    RESULT_BACKEND = 'redis://127.0.0.1:6379/0'
    CELERY_ACCEPT_CONTENT = ['json', 'msgpack', 'yaml']
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_RESULT_SERIALIZER = 'json'

    CELERYBEAT_SCHEDULE = {
        'refresh': {
            'task': 'refresh',
            'schedule': 60
        },
            'check_roster_moves': {
            'task': 'check_roster_moves',
            'schedule': 300
        },
    }
    


class DevelopmentConfig(Config):
    DEBUG = True
    CELERY_TASK_FILE_WRITE_PATH = "/Users/craigh/dev/fantasy_bot"


class ProductionConfig(Config):
    pass

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig
}