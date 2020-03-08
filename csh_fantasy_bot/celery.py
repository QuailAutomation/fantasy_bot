from celery import Celery

app = Celery('tasks', broker='amqp://admin:mypass@192.168.1.20:5672')

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
