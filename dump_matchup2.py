import pandas as pd
import numpy as np
import datetime

from csh_fantasy_bot import bot, nhl, roster_change_optimizer
from csh_fantasy_bot.nhl import score_team


import logging
logging.basicConfig(level=logging.INFO)

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

from elasticsearch import Elasticsearch
from elasticsearch import helpers


import os

week_number = 2


# es = Elasticsearch(hosts='http://192.168.1.20:9200', http_compress=True)
es = Elasticsearch(hosts='http://localhost:9200', http_compress=True)


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

# league_id = '396.l.53432'
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
my_scores = manager.projected_league_scores[my_team_id]

print("My team has {} roster changes available.".format(manager.roster_changes_allowed))
print("Scoring no roster changes:")
print(my_scores.sum())

roster_changes = list()
# roster_changes.append([4248,5710, np.datetime64('2021-01-15')])
# coleman 5441
# foligno 4008
# couture 4248
# in arvidson 6480
# roster_changes.append(roster_change_optimizer.RosterChange(4248, 4020, datetime.date(2021, 1, 13), manager.all_player_predictions.loc[4020, manager.stat_categories + ['eligible_positions', 'team_id', 'fpts']]))
# roster_changes.append([5698,6381, np.datetime64('2020-03-02')])
# roster_changes.append([4792,5405, np.datetime64('2020-02-13')])
# roster_changes.append([4792,5380, np.datetime64('2020-02-15')])

# roster_changes.append(roster_change_optimizer.RosterChange(5984,7267, np.datetime64('2020-02-03')))
# roster_changes.append(roster_change_optimizer.RosterChange(4792,5569, np.datetime64('2020-02-09')))
# roster_changes.append(roster_change_optimizer.RosterChange(5698,5380, np.datetime64('2020-02-04')))
roster_change_set = roster_change_optimizer.RosterChangeSet(roster_changes)
# my_scores = manager.projected_league_scores[my_team_id]
my_scores_with_rc = manager.score_team(manager.all_player_predictions[manager.all_player_predictions.fantasy_status == int(my_team_id)],roster_change_set=roster_change_set, simulation_mode=False)
# (my_team, manager.week, manager.stat_categories, roster_change_set=roster_change_set)
print("Scoring with roster changes:")
print(my_scores_with_rc[1].sum())

manager.score_comparer.print_week_results(my_scores_with_rc[1])
pass

import cProfile, pstats, io


def do_cprofile(func):
    def profiled_func(*args, **kwargs):
        profile = cProfile.Profile()
        try:
            profile.enable()
            result = func(*args, **kwargs)
            profile.disable()
            return result
        finally:
            s = io.StringIO()
            sortby = 'cumulative'
            ps = pstats.Stats(profile).sort_stats(sortby)
            ps.print_stats()

    return profiled_func


#@do_cprofile
def do_run():
    print('profiling')
    # scorer.score(roster_change_set)


do_run()

if len(roster_changes) > 0:
    my_scores = scorer.score(roster_change_set)
    manager.score_comparer.print_week_results(my_scores.sum())


my_scores.to_csv('team-results.csv')
manager.all_players.to_csv('all-players.csv')
# manager.all_players.set_index('player_id', inplace=True)


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