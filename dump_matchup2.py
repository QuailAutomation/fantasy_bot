import pandas as pd
import numpy as np

from csh_fantasy_bot import bot, nhl, roster_change_optimizer

import logging
logging.basicConfig(level=logging.INFO)

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

player_stats = ["G", "A", "+/-", "PIM", "SOG", "FW", "HIT"]

def print_week_results(my_scores_summary):
    sc = manager.score_comparer.compute_score(my_scores_summary)
    differences = my_scores_summary - manager.score_comparer.opp_sum

    means = pd.DataFrame([my_scores_summary, manager.score_comparer.opp_sum]).mean()
    # differences / means
    score = differences / means
    # cat_win = 1 if my_scores.sum() > manager.score_comparer.opp_sum else -1
    summary_df = pd.DataFrame(
        [my_scores_summary, manager.score_comparer.opp_sum, differences, means, manager.score_comparer.league_means, manager.score_comparer.stdevs, score],
        index=['my-scores', 'opponent', 'difference', 'mean-opp','mean-league','std dev', 'score'])
    print(summary_df.head(10))
    print("Score: {:4.2f}".format(sc))


manager: bot.ManagerBot = bot.ManagerBot(18)
print("My team has {} roster changes available.".format(manager.roster_changes_allowed))
scorer = nhl.BestRankedPlayerScorer(manager.lg, manager.tm, manager.ppool, manager.week)
my_scores = scorer.score()
print_week_results(my_scores.loc[:,player_stats].sum())

roster_changes = list()
roster_changes.append([3788,7111, np.datetime64('2020-02-13')])
roster_changes.append([5573,3980, np.datetime64('2020-02-14')])
roster_changes.append([4683,6055, np.datetime64('2020-02-11')])
roster_changes.append([4792,5380, np.datetime64('2020-02-15')])

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


# @do_cprofile
def do_run():
    print('profiling')
    scorer.score(roster_change_set)


do_run()

if len(roster_changes) > 0:
    my_scores = scorer.score(roster_change_set)
    print_week_results(my_scores.loc[:,player_stats].sum())

my_scores.to_csv('team-results.csv')
manager.all_players.to_csv('all-players.csv')
manager.all_players.set_index('player_id', inplace=True)
my_scores.loc[:,'name'] = manager.all_players.loc[my_scores.index,'name']
my_scores.loc[:,'fantasy_team_id'] = manager.tm.team_key.split('.')[-1]
print(my_scores.head(50))

if False:
    from elasticsearch import Elasticsearch
    from elasticsearch import helpers

    es = Elasticsearch(hosts='http://192.168.1.20:9200',http_compress=True)
    my_scores.reset_index(inplace=True)
    use_these_keys = my_scores.columns


    def filterKeys(document):
        return {key: document[key] for key in use_these_keys}


    def doc_generator(df):
        df_iter = df.iterrows()
        for index, document in df_iter:
            yield {
                "_index": 'fantasy-bot-team-results',
                "_type": "_doc",
                "_id": "{}-{}-{}".format(document['player_id'], document['play_date'], document['score_type']),
                "_source": filterKeys(document),
            }


    helpers.bulk(es, doc_generator(my_scores))
