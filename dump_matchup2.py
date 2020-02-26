import pandas as pd
import numpy as np
from datetime import datetime, timezone

from csh_fantasy_bot import bot, nhl, roster_change_optimizer

import logging
logging.basicConfig(level=logging.INFO)

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

from elasticsearch import Elasticsearch
from elasticsearch import helpers

week_number = 20

es = Elasticsearch(hosts='http://192.168.1.20:9200', http_compress=True)


def filter_keys(document, columns):
    return {key: document[key] for key in columns}

def write_team_results_es(scoring_data, team_id):
    '''write out weekly scoring results to ES'''

    scoring_data.loc[:, 'name'] = manager.all_players.loc[scoring_data.index, 'name']
    scoring_data.loc[:, 'week_number'] = week_number
    scoring_data.loc[:, 'fantasy_team_id'] = team_id
    columns = my_scores.columns.tolist()
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



manager: bot.ManagerBot = bot.ManagerBot(week_number)
print("My team has {} roster changes available.".format(manager.roster_changes_allowed))
scorer = nhl.BestRankedPlayerScorer(manager.lg, manager.tm, manager.ppool, manager.week)
my_scores = scorer.score()
manager.score_comparer.print_week_results(my_scores.sum())

roster_changes = list()
roster_changes.append([6376,5639, np.datetime64('2020-02-26')])
# roster_changes.append([6750,6376, np.datetime64('2020-02-23')])
# roster_changes.append([4792,5405, np.datetime64('2020-02-13')])
# roster_changes.append([4792,5380, np.datetime64('2020-02-15')])

# roster_changes.append(roster_change_optimizer.RosterChange(5984,7267, np.datetime64('2020-02-03')))
# roster_changes.append(roster_change_optimizer.RosterChange(4792,5569, np.datetime64('2020-02-09')))
# roster_changes.append(roster_change_optimizer.RosterChange(5698,5380, np.datetime64('2020-02-04')))
roster_change_set = roster_change_optimizer.RosterChangeSet(
    pd.DataFrame(roster_changes, columns=['player_out', 'player_in', 'change_date']),max_allowed=len(roster_changes))

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
    scorer.score(roster_change_set)


do_run()

if len(roster_changes) > 0:
    my_scores = scorer.score(roster_change_set)
    manager.score_comparer.print_week_results(my_scores.sum())


my_scores.to_csv('team-results.csv')
manager.all_players.to_csv('all-players.csv')
manager.all_players.set_index('player_id', inplace=True)


def extract_team_id(team_key):
    return team_key.split('.')[-1]


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
    stats = ['G','A','SOG','+/-','HIT','PIM','FW']
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