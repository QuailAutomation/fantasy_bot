import pandas as pd
import logging

from csh_fantasy_bot.nhl import BestRankedPlayerScorer
from csh_fantasy_bot.league import FantasyLeague
from csh_fantasy_bot.roster import RecursiveRosterBuilder

logging.basicConfig(level=logging.DEBUG)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)


my_team = pd.read_csv('./tests/my-team.csv',
                      converters={"eligible_positions": lambda x: x.strip("[]").replace("'", "").split(", ")})
my_team.set_index('player_id', inplace=True)
my_team.head()
builder = RecursiveRosterBuilder()
# %timeit builder.find_best(my_team)




league = FantasyLeague('396.l.53432')
t = league.team_by_key('396.l.53432.t.2')
date_range = pd.date_range(*league.week_date_range(21))

league = league.as_of(date_range[0])
weights_series =  pd.Series([1, .75, 1, .5, 1, .1, 1], index=league.scoring_categories())
projected_stats = league.get_projections()
projected_stats['fpts'] = 0
projected_stats['fpts'] = projected_stats.loc[projected_stats.G == projected_stats.G,weights_series.index.tolist()].mul(weights_series).sum(1)
scorer = BestRankedPlayerScorer(league, t, projected_stats)

score = None
# for _ in range(20):
#     score = scorer.score(date_range,simulation_mode=True)

print(f'Summary:\n{score.sum()}')