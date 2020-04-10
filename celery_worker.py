from csh_fantasy_bot.factory import create_app, celery
from csh_fantasy_bot.celery_utils import init_celery
app = create_app()
init_celery(celery, app)