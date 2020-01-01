import os
import json
import datetime
import logging
import pandas as pd
import numpy as np

from nhl_scraper.nhl import Scraper
from yahoo_fantasy_api import League, Team
from yahoo_oauth import OAuth2



from csh_fantasy_bot import fantasysp_scrape, utils, roster
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


tm_cache = utils.TeamCache(league.team_key())
lg_cache = utils.LeagueCache()

current_week = league.current_week()
start_week,end_week = league.week_date_range(current_week)
week = pd.date_range(start_week, end_week)

waivers = league.waivers()

my_team: Team= league.to_team(league.team_key())
#roster = my_team.roster(current_week)

nhl_scraper = Scraper()
nhl_teams = nhl_scraper.teams()
nhl_teams.set_index("id")

#weeks_out = 3
#for i,week in enumerate(['GAMESTHISWEEK','GAMESNEXTWEEK','GAMES2WEEKSOUT']):
#    nhl_teams[week] = nhl_teams['id'].map(nhl_scraper.games_count(week_date_range[0]+ timedelta(days=i * 7),
#                                                                  week_date_range[1]+ timedelta(days=i * 7)))
#print(nhl_teams.head(5))
stats = ["G","A","SOG","+/-","HIT","PIM","FW"]


def prediction_loader():
    # module = self._get_prediction_module()
    # func = getattr('csh_fantasy_bot',
    #                self.cfg['Prediction']['builderClassLoader'])
    return fantasysp_scrape.Parser()


expiry = datetime.timedelta(minutes=24 * 60)
fantasysp_p = tm_cache.load_prediction_builder(expiry, prediction_loader)
positions = ['C','LW','RW','D']


def loader():
    fa = league.free_agents(None)
    return fa


expiry = datetime.timedelta(minutes=360)
free_agents = lg_cache.load_free_agents(expiry, loader)

all_mine = my_team.roster()
pct_owned = league.percent_owned([e['player_id'] for e in all_mine])
for p, pct_own in zip(all_mine, pct_owned):
    if p['selected_position'] == 'BN' or \
            p['selected_position'] == 'IR':
        p['selected_position'] = np.nan
    assert(pct_own['player_id'] == p['player_id'])
    p['percent_owned'] = pct_own['percent_owned']

rcont = roster.Container(None, None)
rcont.add_players(free_agents + all_mine)

fantasy_projections = fantasysp_p.predict(rcont)


def lineup_loader():
    lineups = []
    for tm in league.teams():
        tm = league.to_team(tm['team_key'])
        rcont = roster.Container(league, tm)
        lineups.append(fantasysp_p.predict(rcont))

    return lineups

league_lineups = lg_cache.load_league_lineup(datetime.timedelta(days=5),
                                        loader)



#fantasy_projections = fantasy_projections.merge(nhl_teams, left_on='Tm', right_on='abbrev')
#fantasy_projections.rename(columns = {'id':'team_id'}, inplace = True)



# for i in range(7 * weeks_out):
#     days_games = nhl_scraper.games_count(week_date_range[0]+ timedelta(days=i),week_date_range[0]+ timedelta(days=i))
#     merged["DAY{}GAMEPLAYED".format(i)] = merged["team_id"].map(days_games)

opponent_team = league.to_team(my_team.matchup(league.current_week()))
opp_team = roster.Container(league, opponent_team)
opp_df = fantasysp_p.predict(opp_team)
#league_stats = league.stat_categories()

#TODO could incorporate this into roster builder
#league_roster_makeup = league.positions()
opponent_scorer:BestRankedPlayerScorer = BestRankedPlayerScorer(league,opponent_team, opp_df, week)
projected_opponent_score = opponent_scorer.score()

my_scorer:BestRankedPlayerScorer = BestRankedPlayerScorer(league, my_team, fantasy_projections, week)
projected_my_score = my_scorer.score()

def comp(x):
    if x == 0:
        return 0
    return 1 if x > 0 else -1

def print_scoring_header():
    print("{:20}   {:5}   {:5}   {:5}   {:5}   {:5}   {:5}   {:5}".
          format("       ",'G', 'A','+/-', 'PIM', 'SOG', 'FW', 'Hit'))

def print_scoring_results(scoring, title):
    print("{:20}   {:.1f}   {:.1f}    {:.1f}     {:.1f}     {:.1f}   {:.1f}   {:.1f}".
          format(title,
                 scoring['G'], scoring['A'],
                 scoring['+/-'], scoring['PIM'], scoring['SOG'], scoring['FW'], scoring['HIT']))

results = projected_my_score.sum() - projected_opponent_score.sum()
final_line = results.apply( comp )
detail = False
if detail:
    print("My projected score:\n {}".format(projected_my_score))
    print("Opponent projected score:\n {}".format(projected_opponent_score))
else:
    print_scoring_header()
    print_scoring_results(projected_my_score.sum(),'My Team')
    print_scoring_results(projected_opponent_score.sum(),'Opponent')


print_scoring_results(results,'Results')
print_scoring_results(final_line, 'Final Line')
cat_differential = final_line.sum()
print("Final score: {}".format(cat_differential))
    # print("My Totals:r\n {}".format(projected_my_score.sum().T))
    # print("Opp Totals:\n {}".format(projected_opponent_score.sum().T))

#print("Projected result is:\n {}".format(results))
#print(final_line)
pass

