import os
import logging

from celery import Celery
from yahoo_oauth import OAuth2
from yahoo_fantasy_api import League

from csh_fantasy_bot.yahoo_fantasy import check_for_new_changes

oauth = OAuth2(None, None, from_file='oauth2.json')
league: League = League(oauth,'396.l.53432')
leagues = {'396.l.53432':league}

from elasticsearch_dsl import connections
connections.create_connection(hosts=['localhost'], timeout=20)

rabbit_url = os.environ.get('CELERY_BROKER_URL', 'amqp://admin:mypass@rabbitmq:5672')
app = Celery('tasks', broker=rabbit_url)

app.conf.beat_schedule = {
  # 'refresh': {
  #   'task': 'refresh',
  #   'schedule': 60
  # },
    'check_roster_moves': {
    'task': 'check_roster_moves',
    'schedule': 300
  },
}


@app.task(bind=True, name='refresh')
def refresh(self):
    print('refresh called')
    return 'Success'

@app.task(bind=True, name='check_roster_moves')
def check_roster_moves(self):
    found_new_moves = check_for_new_changes(league, True)
    logging.debug("found new roster moves: {}".format(found_new_moves))
    if found_new_moves:
        flush_caches.delay(league.league_id)
    return True

@app.task(bind=True, name='flush_caches')
def flush_caches(self, league_id):
    logging.info('Flush Cache: {}'.format(league_id))
    return True
