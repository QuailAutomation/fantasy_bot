import os
import json
import datetime
import logging
import pandas as pd
from pandas import ExcelWriter
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

current_week = 14
start_week,end_week = league.week_date_range(current_week)
week = pd.date_range(start_week, end_week)
opponent_id = my_team.matchup(current_week)
opponent_team = league.to_team(opponent_id)


def _get_team_name(lg, team_key):
    for team in lg.teams():
        if team['team_key'] == team_key:
            return team['name']
    raise LookupError("Could not find team for team key: {}".format(
        team_key))

print("Opponent: {}".format(_get_team_name(league,opponent_id)))

# scoreboard = league.scoreboard()
# standings = league.standings()
# nhl_scraper = Scraper()
# nhl_teams = nhl_scraper.teams()
# nhl_teams.set_index("id")
matchups = league.matchups()


def get_roster_adds(raw_matchups ,team_id):
    def retrieve_attribute_from_team_info(team_info, attribute):
        for attr in team_info:
            if attribute in attr:
                return attr[attribute]

    num_matchups = raw_matchups['fantasy_content']['league'][1]['scoreboard']['0']['matchups']['count']
    for matchup_index in range(0,num_matchups):
        matchup = raw_matchups['fantasy_content']['league'][1]['scoreboard']['0']['matchups'][str(matchup_index)]
        for i in range(0,2):
            try:
                if int(retrieve_attribute_from_team_info(matchup['matchup']['0']['teams'][str(i)]['team'][0],'team_id')) == team_id:
                    return int(retrieve_attribute_from_team_info(matchup['matchup']['0']['teams'][str(i)]['team'][0],'roster_adds')['value'])
            except TypeError as e:
                pass
    raise LookupError("team id not found: {}".format(team_id))


# roster_add_list = [get_roster_adds(matchups, id) for id in range(1,9)]

stats = ["G","A","SOG","+/-","HIT","PIM","FW"]

def prediction_loader():
    return fantasysp_scrape.Parser()

expiry = datetime.timedelta(minutes=6 * 24 * 60)
fantasysp_p = tm_cache.load_prediction_builder(None, prediction_loader)


def loader():
    fa = league.free_agents(None)
    return fa

expiry = datetime.timedelta(minutes=6 * 60)
free_agents = lg_cache.load_free_agents(expiry, loader)
my_roster =  my_team.roster(day=start_week)
opponent_roster = opponent_team.roster(day=start_week)
fantasy_projections = fantasysp_p.predict(pd.DataFrame(free_agents + my_roster + opponent_roster))
# excel_writer = ExcelWriter("scores.xlsx")
my_scorer:BestRankedPlayerScorer = BestRankedPlayerScorer(league, my_team, fantasy_projections, week)
# my_scorer.register_excel_writer(excel_writer)
opp_scorer:BestRankedPlayerScorer = BestRankedPlayerScorer(league, opponent_team, fantasy_projections, week)

roster_changes = []
#roster_changes.append(roster_change_optimizer.RosterChange(3652,5573, np.datetime64('2020-01-12')))
#roster_changes.append(roster_change_optimizer.RosterChange(6750,6448, np.datetime64('2020-01-12')))
# roster_changes.append(roster_change_optimizer.RosterChange(3982,5573, np.datetime64('2020-01-09')))
# roster_changes.append(roster_change_optimizer.RosterChange(5697,5626, np.datetime64('2019-12-11')))
roster_change_set = roster_change_optimizer.RosterChangeSet(roster_changes)

# projected_my_score = my_scorer.score()
projected_my_score = my_scorer.score(roster_change_set)
projected_my_score.to_csv("myscore.csv")
opponent_score = opp_scorer.score()
opponent_score.to_csv("opponent.csv")
# excel_writer.save()

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


detail = True
if detail:
    print(projected_my_score.head(20))

else:
    print_scoring_header()

print_scoring_results(projected_my_score.sum(),'My Team')
print_scoring_results(opponent_score.sum(),'Opponent Team')
print_scoring_results(projected_my_score[stats].sum().subtract(opponent_score[stats].sum()),"Diff")


def save_xls(list_dfs, xls_path):
    with ExcelWriter(xls_path) as writer:
        for n, df in enumerate(list_dfs):
            df.to_excel(writer,'sheet%s' % n)
        writer.save()
