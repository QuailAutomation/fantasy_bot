import timeit

# setup = '''\
import pandas as pd
import logging

from csh_fantasy_bot.nhl import BestRankedPlayerScorer, score_team
from csh_fantasy_bot.league import FantasyLeague
from csh_fantasy_bot.roster import RecursiveRosterBuilder

logging.basicConfig(level=logging.DEBUG)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

league = FantasyLeague('396.l.53432')
date_range = pd.date_range(*league.week_date_range(21))

league = league.as_of(date_range[0])
weights_series =  pd.Series([1, .75, 1, .5, 1, .1, 1], index=league.scoring_categories())

score = None
# for _ in range(20):
my_team = pd.read_csv('./tests/my-team.csv',
                    converters={"eligible_positions": lambda x: x.strip("[]").replace("'", "").split(", ")})
my_team.set_index('player_id', inplace=True)
my_team = my_team.query('position_type == "P" & status != "IR"')

tracked_stats = league.scoring_categories()
# set up available players
# projected_stats = league.get_projections().query('position_type == "P" & status != "IR" & fantasy_status == 2').loc[:,tracked_stats + ['eligible_positions', 'team_id']]
projected_stats = my_team
projected_stats['fpts'] = 0
projected_stats['fpts'] = projected_stats.loc[projected_stats.G == projected_stats.G,weights_series.index.tolist()].mul(weights_series).sum(1)

results = score_team(projected_stats, date_range, tracked_stats)

print('Done set up')
# score = scorer.score(date_range,simulation_mode=True)
num_repeats = 100
print(min(timeit.repeat('score_team(projected_stats, date_range, tracked_stats)', number=num_repeats,repeat=5, globals=globals()))/num_repeats)
# print(f'Summary:\n{score.sum()}')