"""Celery Tasks."""
import time
import random
import json
import logging
import pandas as pd
import jsonpickle
import jsonpickle.ext.pandas as jsonpickle_pandas

from csh_fantasy_bot.extensions import celery

from functools import partial
from csh_fantasy_bot.nhl import score_team as nhl_score_team

from celery import shared_task, group, chain

jsonpickle_pandas.register_handlers()
log = logging.getLogger(__name__)

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
    """Check if there have been roster transactions since last check."""
    from csh_fantasy_bot.yahoo_fantasy import check_for_new_changes
    found_new_moves = check_for_new_changes(league, True)
    log.debug("found new roster moves: {}".format(found_new_moves))
    if found_new_moves:
        flush_caches.delay(league.league_id)
    return True

@celery.task(bind=True, name='flush_caches')
def flush_caches(self, league_id):
    """Flush caches, there roster moves detected."""
    log.info('Flush Cache: {}'.format(league_id))
    return True

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

@celery.task(bind=True, name='run_ga')
def run_ga(self,league_id='396.l.53432', week=None):
    """Start genetic algorithm."""
    from csh_fantasy_bot import automation
    driver = automation.Driver(week)
    driver.run()

league = None  
CHUNK_SIZE = 15
log.debug(f'chunk size for scoring is{CHUNK_SIZE}')

@shared_task
def do_chunk(team_key, start_date, end_date, roster_change_sets_jp, opponent=None):
    roster_change_sets = jsonpickle.decode(roster_change_sets_jp)
    def chunker(seq, size):
        return (seq[pos:pos + size] for pos in range(0, len(seq), size))
    return team_key, start_date, end_date, jsonpickle.encode([roster_change_chunk for roster_change_chunk in chunker(roster_change_sets,CHUNK_SIZE)]), opponent


# @celery.task(bind=True, name='score_team')
@shared_task
def score_team(player_projections, start_date, end_date, scoring_categories, roster_change_sets_jp):
    """Score a team by applying roster change sets."""
    # team_key, start_date, end_date, roster_change_sets_jp, opponent = params
    # log.debug(f"Scoring team offset is{offset}")
    # '396.l.53432.t.2' - league key is first 3 parts
    roster_change_sets = jsonpickle.decode(roster_change_sets_jp)
    if roster_change_sets:
        # league_key = ".".join(team_key.split('.')[:3])
        date_range = pd.date_range(start_date, end_date)
        # TODO figure out player projections....players on team and players getting added via roster change
        roster = jsonpickle.decode(player_projections)
        # json pickle seems to be decoding eligble_positions back into str...should be list
        roster['eligible_positions'] = pd.eval(roster['eligible_positions'])
        
        # score = partial(nhl_score_team, roster, date_range, scoring_categories)
        
        if roster_change_sets:
            log.debug(f"starting scoring for len change_sets {len(roster_change_sets)}")
            the_scores = (nhl_score_team(roster, date_range, scoring_categories, rc) for rc in roster_change_sets)
            log.debug("done scoring")
            # just serialize the id of the roster change
            return jsonpickle.encode([(rc._id,score) for rc,score in the_scores])
    else:
        return []
    

def score(team_key, start_date, end_date, roster_change_sets, opponent=None):
    return jsonpickle.decode(score_team.delay((team_key, start_date, end_date, jsonpickle.encode(roster_change_sets), opponent)).get())

def chunks(lst, n): 
        """Yield successive n-sized chunks from lst.""" 
        for i in range(0, len(lst), n): 
            yield lst[i:i + n ]

def score_chunk(team_roster, start_date, end_date, roster_change_sets, scoring_categories):
    count_words = group([score_team.s(jsonpickle.encode(i)) for i in chunks(roster_change_sets,CHUNK_SIZE)])
    # jsonpickle.encode(i)                  
    log.debug(f"start score, # roster change sets: {len(roster_change_sets)}")
    return_val =  count_words(jsonpickle.encode(team_roster), start_date, end_date, scoring_categories)
    
    final_results = []
    for result in return_val.get():
        if result:
            rcs = jsonpickle.decode(result)
            for rc in rcs:
                final_results.append(rc)
    log.debug("done scoring")  
    return final_results
