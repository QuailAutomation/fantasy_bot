import pandas as pd
import numpy as np
import datetime

from csh_fantasy_bot import bot, roster_change_optimizer
from csh_fantasy_bot.nhl import score_team


import logging
logging.basicConfig(level=logging.INFO)

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

from elasticsearch import Elasticsearch
from elasticsearch import helpers


import os


# es = Elasticsearch(hosts='http://192.168.1.20:9200', http_compress=True)
es = Elasticsearch(hosts='http://localhost:9200', http_compress=True)

def to_roster_change(roster_changes, player_df):
    """
    Date: 2021-02-06, in: Vladislav Namestnikov(5388), out: Kevin Hayes(4984)
    Date: 2021-02-04, in: Dylan Strome(6745), out: Jeff Carter(3349)
    Date: 2021-02-05, in: Alexis Lafreniere(8641), out: Darnell Nurse(5986)
    """
    rcs = roster_change_optimizer.RosterChangeSet()
    for rc_line in roster_changes.split('\n'):
        if rc_line != '':
            roster_change_parts = rc_line.split(',')
            change_date = datetime.datetime.strptime(roster_change_parts[0].split(':')[-1].strip(), '%Y-%m-%d').date()
            string = roster_change_parts[1]
            in_player_id = int(string[string.find("(")+1:string.find(")")])
            string = roster_change_parts[2]
            out_player_id = int(string[string.find("(")+1:string.find(")")])
            rcs.add(roster_change_optimizer.RosterChange(out_player_id, in_player_id, change_date, player_df.loc[in_player_id]))
        # roster_changes.append(roster_change_optimizer.RosterChange) 
    return rcs

def filter_keys(document, columns):
    return {key: document[key] for key in columns}

def write_team_results_es(scoring_data, team_id):
    '''write out weekly scoring results to ES'''
    scoring_data['timestamp'] = scoring_data['play_date']
    scoring_data.loc[:, 'name'] = manager.all_players.loc[scoring_data.index, 'name']
    scoring_data.loc[:, 'week_number'] = week_number
    scoring_data.loc[:, 'fantasy_team_id'] = team_id
    columns = scoring_data.columns.tolist()
    columns.append('player_id')
    data = scoring_data.reset_index()

    def doc_generator_team_results(df):
        df_iter = df.iterrows()
        for index, document in df_iter:
            # document['player_id'] = index
            yield {
                "_index": 'fantasy-bot-team-results',
                "_type": "_doc",
                "_id": "{}.{}.{}".format(document['player_id'], document['play_date'], document['score_type']),
                "_source": filter_keys(document, columns),
            }

    helpers.bulk(es, doc_generator_team_results(data))

week_number = 4

league_id = '403.l.41177'
# league_id = "403.l.18782"

simulation_mode = False
manager: bot.ManagerBot = None
if 'YAHOO_OAUTH_FILE' in os.environ:
    auth_file = os.environ['YAHOO_OAUTH_FILE']
    manager = bot.ManagerBot(week_number,oauth_file=auth_file, league_id=league_id, simulation_mode=simulation_mode)
else:
    manager = bot.ManagerBot(week_number, league_id=league_id, simulation_mode=simulation_mode)


my_team_id = manager.tm.team_key.split('.')[-1]

my_opponent_id = manager.opp_team_key
my_scores = manager.my_team.scores()
# print("My team has {} roster changes available.".format(manager.roster_changes_allowed))
# print("Scoring no roster changes:")
# print(my_scores.sum())

roster_change_string = """
"""
roster_change_set = to_roster_change(roster_change_string, manager.all_player_predictions[manager.stat_categories + ['fpts']])

test = manager.score_team(roster_change_set=roster_change_set)
my_scores_with_rc = manager.score_team(manager.all_player_predictions[manager.all_player_predictions.fantasy_status == int(my_team_id)],roster_change_set=roster_change_set, simulation_mode=False)

score_sum = manager.score_comparer.score(manager.my_team.scores())

print(f"Opponent is: {manager.opp_team_name}")
print(score_sum)

# df = manager.my_team.scores().reset_index()
# df1 = df.my_team.scores().set_index(['play_date', 'player_id'])
# df1.loc[('2021-02-02', slice(None)),:].sum()

# manager.score_comparer.print_week_results(my_scores_with_rc[1])
pass

# do_run()

# if len(roster_changes) > 0:
#     my_scores = scorer.score(roster_change_set)
#     manager.score_comparer.print_week_results(my_scores.sum())


# my_scores.to_csv('team-results.csv')
# manager.all_players.to_csv('all-players.csv')
# # manager.all_players.set_index('player_id', inplace=True)


def extract_team_id(team_key):
    return int(team_key.split('.')[-1])


if False:
    write_team_results_es(my_scores, extract_team_id(manager.tm.team_key))
    # dump projections

    opp_scores = manager.opp_sum
    write_team_results_es(opp_scores, extract_team_id(manager.opp_team_key))

    projections = manager.all_players[manager.all_players.position_type == 'P']
    projections.reset_index(inplace=True)

    projections = manager.pred_bldr.predict(projections)
    # projections = projections.replace(np.nan, '', regex=True)
    # projection_date = datetime(2020,2,10, tzinfo=timezone.utc)
    projection_date = datetime.now(tz=timezone.utc).date()
    projections.loc[:, 'projection_date'] = projection_date

    player_projection_columns =['name','eligible_positions','team_id','team_name','projection_date','player_id'] + stats


    def doc_generator_projections(df):
        df_iter = df.iterrows()
        for index, document in df_iter:
            try:
                document['player_id'] = int(index)
                if not np.isnan(document['G']):
                    yield {
                        "_index": 'fantasy-bot-player-projections',
                        "_type": "_doc",
                        "_id": "{}.{}".format(index,projection_date),
                        "_source": filter_keys(document,player_projection_columns),
                    }
            except Exception as e:
                print(e)
                pass


    helpers.bulk(es, doc_generator_projections(projections))
    pass