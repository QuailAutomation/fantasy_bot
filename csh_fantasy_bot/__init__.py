import os
import logging
from celery import Celery

rabbit_url = os.environ.get('CELERY_BROKER_URL', 'amqp://guest:guest@localhost:5672')

def make_celery(app_name=__name__):
    """ Connect celery to broker."""
    backend = "redis://localhost:6379/0"
    broker = rabbit_url
    logging.info(f"Celery connecting to rabbit broker {broker}")
    return Celery(app_name, broker=broker) # backend=backend,

celery = make_celery()