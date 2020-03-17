import os
from celery import Celery

rabbit_url = os.environ['CELERY_BROKER_URL', 'amqp://admin:mypass@rabbitmq:5672']
app = Celery('tasks', broker=rabbit_url)

app.conf.beat_schedule = {
  'refresh': {
    'task': 'refresh',
    'schedule': 10
  },
}


@app.task(bind=True, name='refresh')
def refresh(self):
    print('refresh called')
    return 'Success'
