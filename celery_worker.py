from csh_fantasy_bot import celery
from csh_fantasy_bot.factory import create_app
from csh_fantasy_bot.celery_utils import init_celery
app = create_app()
init_celery(celery, app)