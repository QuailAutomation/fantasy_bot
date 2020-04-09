"""Config for Celery."""
from celery.schedules import crontab


# CELERY_IMPORTS = ('csh_fantasy_bot.tasks')
class Config(object):
    CELERY_TASK_RESULT_EXPIRES = 30
    CELERY_TIMEZONE = 'US/Pacific'
    BROKER_URL = 'amqp://guest:guest@localhost:5672'
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
   


class ProductionConfig(Config):
    pass

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig
}