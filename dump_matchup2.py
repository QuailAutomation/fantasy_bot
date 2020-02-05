import pandas as pd
import numpy as np

from csh_fantasy_bot import bot, nhl, roster_change_optimizer, roster

import logging
logging.basicConfig(level=logging.DEBUG)

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)


def print_week_results(my_scores_summary):
    sc = manager.score_comparer.compute_score(my_scores_summary)
    differences = my_scores_summary - manager.score_comparer.opp_sum
    score = differences/manager.score_comparer.stdevs
    # cat_win = 1 if my_scores.sum() > manager.score_comparer.opp_sum else -1
    summary_df = pd.DataFrame([my_scores_summary, manager.score_comparer.opp_sum, differences, manager.score_comparer.stdevs, score], index=['my-scores', 'opponent', 'difference', 'std dev', 'score'])
    print(summary_df.head(10))
    print("Score: {:4.2f}".format(sc))


manager: bot.ManagerBot = bot.ManagerBot(17)
scorer = nhl.BestRankedPlayerScorer(manager.lg,manager.tm,manager.ppool,manager.week)
scorer.roster_builder = roster.RecursiveRosterBuilder()
my_scores = scorer.score()
print_week_results(my_scores.sum())

roster_changes = []
#roster_changes.append([6390,5260, np.datetime64('2020-02-03')])
# roster_changes.append(roster_change_optimizer.RosterChange(5984,7267, np.datetime64('2020-02-03')))
# roster_changes.append(roster_change_optimizer.RosterChange(4792,5569, np.datetime64('2020-02-09')))
# roster_changes.append(roster_change_optimizer.RosterChange(5698,5380, np.datetime64('2020-02-04')))
roster_change_set = roster_change_optimizer.RosterChangeSet(roster_changes)

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

@do_cprofile
def do_run():
    print('profiling')
    # scorer.roster_builder = roster.RecursiveRosterBuilder()
    scorer.score(roster_change_set)

do_run()


if len(roster_changes) > 0:
    my_scores_with_roster_changes = scorer.score(roster_change_set)
    print_week_results(my_scores_with_roster_changes.sum())

