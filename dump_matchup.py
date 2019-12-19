import os
import json
import datetime
import logging
import pandas as pd
import numpy as np

from nhl_scraper.nhl import Scraper
from yahoo_fantasy_api import League, Team
from yahoo_oauth import OAuth2



from csh_fantasy_bot import fantasysp_scrape, utils, roster, roster_change_optimizer
from csh_fantasy_bot.nhl import BestRankedPlayerScorer

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

import logging
logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

if not os.path.exists('oauth2.json'):
    creds = {'consumer_key': 'my_key', 'consumer_secret': 'my_secret'}
    with open('oauth2.json', "w") as f:
        f.write(json.dumps(creds))

oauth = OAuth2(None, None, from_file='oauth2.json')

league = League(oauth,'396.l.53432')
my_team: Team= league.to_team(league.team_key())

tm_cache = utils.TeamCache(league.team_key())
lg_cache = utils.LeagueCache()

current_week = league.current_week()
start_week,end_week = league.week_date_range(11)
week = pd.date_range(start_week, end_week)



# nhl_scraper = Scraper()
# nhl_teams = nhl_scraper.teams()
# nhl_teams.set_index("id")

stats = ["G","A","SOG","+/-","HIT","PIM","FOW"]

def prediction_loader():
    return fantasysp_scrape.Parser()

expiry = datetime.timedelta(minutes=6 * 24 * 60)
fantasysp_p = tm_cache.load_prediction_builder(expiry, None)
positions = ['C','LW','RW','D']


def loader():
    fa = league.free_agents(None)
    return fa


# expiry = datetime.timedelta(minutes=360)
free_agents = lg_cache.load_free_agents(None, loader)

fantasy_projections = fantasysp_p.predict(pd.DataFrame(free_agents + my_team.roster()))

my_scorer:BestRankedPlayerScorer = BestRankedPlayerScorer(pd.DataFrame(my_team.roster()), fantasy_projections, week)

roster_changes = []
roster_changes.append(roster_change_optimizer.RosterChange(5462,6402, np.datetime64('2019-12-19')))
roster_changes.append(roster_change_optimizer.RosterChange(3788,6571, np.datetime64('2019-12-22')))
# roster_changes.append(roster_change_optimizer.RosterChange(3357,1700, np.datetime64('2019-12-13')))
# roster_changes.append(roster_change_optimizer.RosterChange(5697,5626, np.datetime64('2019-12-11')))
roster_change_set = roster_change_optimizer.RosterChangeSet(roster_changes)

projected_my_score = my_scorer.score()
# projected_my_score = my_scorer.score(roster_change_set)


def comp(x):
    if x == 0:
        return 0
    return 1 if x > 0 else -1

def print_scoring_header():
    print("{:20}   {:5}   {:5}   {:5}   {:5}   {:5}   {:5}   {:5}".
          format("       ",'G', 'A','+/-', 'PIM', 'SOG', 'FOW', 'Hit'))

def print_scoring_results(scoring, title):
    print("{:20}   {:.1f}   {:.1f}    {:.1f}     {:.1f}     {:.1f}   {:.1f}   {:.1f}".
          format(title,
                 scoring['G'], scoring['A'],
                 scoring['+/-'], scoring['PIM'], scoring['SOG'], scoring['FOW'], scoring['HIT']))


detail = True
if detail:
    print(projected_my_score.head(20))

else:
    print_scoring_header()

print_scoring_results(projected_my_score.sum(),'My Team')

