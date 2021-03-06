import logging
import os
import json
import datetime

import pandas as pd
import numpy as np

from yahoo_fantasy_api import Team
from csh_fantasy_bot import fantasysp_scrape, utils
from csh_fantasy_bot.league import FantasyLeague

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

logger = logging.getLogger(__name__)

def lookup_player(player_name, fantasy_projections):
    return "craig: {}".format(fantasy_projections[fantasy_projections.name.str.contains(player_name)].T)


def lookup_player_id(player_id, fantasy_projections):
    return "craig: {}".format(fantasy_projections.loc[player_id])


def do_lookup():
    league = FantasyLeague('396.l.53432')
    # my_team: Team= league.to_team(league.team_key())
    all_players = league._all_players()
    
    tm_cache = utils.TeamCache(league.team_key())

    league_scoring_categories = league.scoring_categories()
    # set up projections and create weighted score (fpts)
    weights_series =  pd.Series([1, .75, 1, .5, 1, .1, 1], index=league_scoring_categories)
    league.as_of(datetime.datetime.now())
    fantasy_projections = league.get_projections()
    fantasy_projections['fpts'] = 0
    fantasy_projections['fpts'] = fantasy_projections.loc[fantasy_projections.G == fantasy_projections.G,weights_series.index.tolist()].mul(weights_series).sum(1)

    print("This utility can look up league players by string(name contains) or id")
    while True:
        # self._print_main_menu()
        print("Player name or id (int) to search for:")
        opt = input()
        # if opt is str, lookup name
        # else lookup by id
        try:
            player_id = int(opt)
            print("Player Info: {}".format(lookup_player_id(player_id, fantasy_projections)))
        except ValueError:
            print("Player Info: {}".format(lookup_player(opt, fantasy_projections)))
        except KeyError:
            print("player id not found")




if __name__ == "__main__":
    do_lookup()
    pass