import pandas as pd
import numpy as np
from datetime import datetime, timezone

from csh_fantasy_bot import bot, nhl, roster_change_optimizer

import logging
logging.basicConfig(level=logging.INFO)

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

week_number = 18
manager: bot.ManagerBot = bot.ManagerBot(week_number)
print("My team has {} roster changes available.".format(manager.roster_changes_allowed))
scorer = nhl.BestRankedPlayerScorer(manager.lg, manager.tm, manager.ppool, manager.week)
my_scores = scorer.score()
manager.score_comparer.print_week_results(my_scores.sum())

roster_changes = list()
roster_changes.append([5573,4978, np.datetime64('2020-02-13')])
roster_changes.append([4792,5405, np.datetime64('2020-02-13')])
# roster_changes.append([3788,3980, np.datetime64('2020-02-13')])
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
my_scores.loc[:,'name'] = manager.all_players.loc[my_scores.index,'name']
my_scores.loc[:,'fantasy_team_id'] = manager.tm.team_key.split('.')[-1]
my_scores.loc[:,'week_number'] = week_number


if True:
    from elasticsearch import Elasticsearch
    from elasticsearch import helpers

    es = Elasticsearch(hosts='http://192.168.1.20:9200',http_compress=True)
    my_scores.reset_index(inplace=True)
    use_these_keys = my_scores.columns


    def filterKeys(document, columns):
        return {key: document[key] for key in columns}


    def doc_generator_team_results(df):
        df_iter = df.iterrows()
        for index, document in df_iter:
            yield {
                "_index": 'fantasy-bot-team-results',
                "_type": "team-results",
                "_id": "{}-{}-{}".format(document['player_id'], document['play_date'], document['score_type']),
                "_source": filterKeys(document,use_these_keys),
            }


    helpers.bulk(es, doc_generator_team_results(my_scores))

    # dump projections

    projections = manager.all_players[manager.all_players.position_type == 'P']
    projections.reset_index(inplace=True)

    projections = manager.pred_bldr.predict(projections)
    # projections = projections.replace(np.nan, '', regex=True)
    projection_date = datetime(2020,2,10, tzinfo=timezone.utc)
    projections.loc[:, 'projection_date'] = projection_date
    stats = ['G','A','SOG','+/-','HIT','PIM','FW']
    player_projection_columns =['name','eligible_positions','team_id','team_name','projection_date'] + stats
    def doc_generator_projections(df):
        df_iter = df.iterrows()
        for index, document in df_iter:
            try:
                if not np.isnan(document['G']):
                    yield {
                        "_index": 'fantasy-bot-player-projections',
                        "_type": "player_projections",
                        "_id": "{}".format(index),
                        "_source": filterKeys(document,player_projection_columns),
                    }
            except Exception as e:
                pass


    helpers.bulk(es, doc_generator_projections(projections))
    pass