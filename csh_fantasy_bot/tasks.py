import time
import random
import logging

from yahoo_oauth import OAuth2
from csh_fantasy_bot.league import FantasyLeague

from csh_fantasy_bot.extensions import celery


oauth = OAuth2(None, None, from_file='oauth2.json')
league = FantasyLeague('396.l.53432')
# leagues = {'396.l.53432':league}


@celery.task()
def make_file(fname, content):
    with open(fname, "w") as f:
        f.write(content)


@celery.task(bind=True)
def long_task(self):
    """Background task that runs a long function with progress reports."""
    verb = ['Starting up', 'Booting', 'Repairing', 'Loading', 'Checking']
    adjective = ['master', 'radiant', 'silent', 'harmonic', 'fast']
    noun = ['solar array', 'particle reshaper', 'cosmic ray', 'orbiter', 'bit']
    message = ''
    total = random.randint(10, 50)
    for i in range(total):
        if not message or random.random() < 0.25:
            message = '{0} {1} {2}...'.format(random.choice(verb),
                                              random.choice(adjective),
                                              random.choice(noun))
        self.update_state(state='PROGRESS',
                          meta={'current': i, 'total': total,
                                'status': message})
                                
        time.sleep(1)
    return {'current': 100, 'total': 100, 'status': 'Task completed!',
            'result': 42}


@celery.task(bind=True, name='check_roster_moves')
def check_roster_moves(self):
    from csh_fantasy_bot.yahoo_fantasy import check_for_new_changes
    found_new_moves = check_for_new_changes(league, True)
    logging.debug("found new roster moves: {}".format(found_new_moves))
    if found_new_moves:
        flush_caches.delay(league.league_id)
    return True


@celery.task(bind=True, name='flush_caches')
def flush_caches(self, league_id):
    logging.info('Flush Cache: {}'.format(league_id))
    return True


@celery.task(bind=True, name='refresh')
def refresh(self):
    """Dummy task."""
    print('refresh called')
    return 'Success'

@celery.task(bind=True, name='load_draft')
def load_draft(self, league_id):
    """Load draft results and stuff into ES."""
    from csh_fantasy_bot.yahoo_fantasy_tasks.draft import export_draft_es
    return export_draft_es(league_id)

@celery.task(bind=True, name='export_boxscores')
def export_boxscores(self):
    """Load boxscores and stuff into ES."""
    from csh_fantasy_bot.yahoo_fantasy_tasks.boxscores import export_boxscores
    return export_boxscores()

@celery.task(bind=True, name='generate_player_predictions')
def generate_player_predictions(self):
    """Generate player preictions and save pickle file."""
    # from csh_fantasy_bot.yahoo_fantasy_tasks.boxscores import export_boxscores
    # return export_boxscores()

@celery.task(bind=True, name='export_teams_results')
def export_teams_results(self,league_id=None, start_date=None,end_date=None):
    """Export the results for each fantasy team to ES."""
    from csh_fantasy_bot.yahoo_fantasy_tasks.team import export_results
    export_results(league_id, start_date, end_date)