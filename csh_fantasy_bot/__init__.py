import os
import logging
from celery import Celery
from csh_fantasy_bot.celeryconfig import config


def make_celery(app_name=__name__):

    config_name = os.environ.get('CONFIG', 'development')
    backend = "redis://localhost:6379/0"
    broker = backend.replace("0", "1")
    # rabbit_url = os.environ.get('CELERY_BROKER_URL', 'amqp://guest:guest@localhost:5672')
    logging.info(f"app_name is {app_name}")
    celery= Celery(app_name, backend=backend)
    celery.config_from_object(config[config_name])    
    return celery
celery = make_celery()



# celery.conf.update(CELERYBEAT_SCHEDULE)


# import os
# import logging
# from celery import Celery

# rabbit_url = os.environ.get('CELERY_BROKER_URL', 'amqp://guest:guest@localhost:5672')

# CELERY_TASK_LIST = [
#     'csh_fantasy_bot.tasks'
# ]

# def make_celery(app_name=__name__):
#     """Connect celery to broker."""
#     backend = "redis://localhost:6379/0"
#     broker = rabbit_url
#     logging.info(f"Celery connecting to rabbit broker {broker}")
#     app = Celery(app_name, broker=broker, include=CELERY_TASK_LIST) # backend=backend,
#     app.conf.beat_schedule = {
#   'refresh': {
#     'task': 'refresh',
#     'schedule': 60
#   },
#     'check_roster_moves': {
#     'task': 'check_roster_moves',
#     'schedule': 300
#   },
# }
#     return app

# celery = make_celery()