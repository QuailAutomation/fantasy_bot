"""Instantiate celery into flask Context."""
def init_celery(celery, app):
    """Instantiate celery into flask Context."""
    celery.conf.update(app.config)
    TaskBase = celery.Task
    class ContextTask(TaskBase):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)
    celery.Task = ContextTask

    # app.conf.beat_schedule = {
    #                             'refresh': {
    #                                 'task': 'refresh',
    #                                 'schedule': 60
    #                             },
    #                                 'check_roster_moves': {
    #                                 'task': 'check_roster_moves',
    #                                 'schedule': 300
    #                             },
    #                         }