import pandas as pd
import logging
import timeit

from csh_fantasy_bot.nhl import BestRankedPlayerScorer
from csh_fantasy_bot.league import FantasyLeague
from csh_fantasy_bot.roster import RecursiveRosterBuilder

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

logging.basicConfig(level=logging.INFO)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

my_team = pd.read_csv('./tests/my-team.csv',
            converters={"eligible_positions": lambda x: x.strip("[]").replace("'", "").split(", ")})
my_team.set_index('player_id', inplace=True)
my_team = my_team.query('position_type != "G" & status != "IR"')
player_stats = ["G", "A", "+/-", "PIM", "SOG", "FW", "HIT"]
weights_series = pd.Series([1, .75, .5, .5, 1, .1, 1], index=player_stats)
player_stats = list(weights_series.index.values)
# drop irs
# avail_players = avail_players[['IR' not in l for l in avail_players.eligible_positions.values.tolist()]]

my_team.loc[:,'fpts'] = my_team[player_stats].mul(weights_series).sum(1)
sorted_players = my_team.sort_values(by=['fpts'], ascending=False)
builder = RecursiveRosterBuilder()
builder.find_best(sorted_players)

# @do_cprofile
def do_run():
   
    
    # builder.find_best(sorted_players)

    print(timeit.timeit('builder.find_best(sorted_players)', number=1000, globals=globals())/1000)



if __name__ == "__main__":
    do_run()
# print(f'Summary:\n{score.sum()}')