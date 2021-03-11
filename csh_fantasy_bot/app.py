import logging

from flask import Flask

from csh_fantasy_bot.extensions import celery

log = logging.getLogger(__name__)

def create_app(testing=False, cli=False):
    """Application factory, used to create application."""
    app = Flask('csh_fantasy_bot')
    app.config.from_object("csh_fantasy_bot.config")

    if testing is True:
        app.config["TESTING"] = True
    ''
    init_celery(app)

    return app


def init_celery(app=None):
    app = app or create_app()
    celery.conf.BROKER_URL = app.config["CELERY_BROKER_URL"]
    # celery.conf.result_backend = app.config["CELERY_RESULT_BACKEND"]
    log.info('Setting celery config')
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        """Make celery tasks work with Flask app context."""
        
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery



if __name__ == "__main__":
    init_celery()