import logging
import os
import json
import datetime

import pandas as pd
import numpy as np

from yahoo_fantasy_api import League, Team
from yahoo_oauth import OAuth2

from csh_fantasy_bot import fantasysp_scrape, utils

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

logger = logging.getLogger(__name__)

if not os.path.exists('oauth2.json'):
    creds = {'consumer_key': 'my_key', 'consumer_secret': 'my_secret'}
    with open('oauth2.json', "w") as f:
        f.write(json.dumps(creds))

oauth = OAuth2(None, None, from_file='oauth2.json')

league = League(oauth,'396.l.53432')
my_team: Team= league.to_team(league.team_key())

tm_cache = utils.TeamCache(league.team_key())
fantasysp_p = tm_cache.load_prediction_builder(None, None)
# positions = ['C','LW','RW','D']


def loader():
    fa = league.all_players()
    return fa


lg_cache = utils.LeagueCache()
# expiry = datetime.timedelta(minutes=360)
all_players = lg_cache.load_all_players(None, None)
fantasy_projections = fantasysp_p.predict(pd.DataFrame(all_players))


def lookup_player(player_name):
    return "craig: {}".format(fantasy_projections[fantasy_projections.name.str.contains(player_name)])


def lookup_player_id(player_id):
    return "craig: {}".format(fantasy_projections.loc[player_id])


print ("This utility can look up league players by string(name contains) or id")
while True:
    # self._print_main_menu()
    print("Player name or id (int) to search for:")
    opt = input()
    # if opt is str, lookup name
    # else lookup by id
    try:
        player_id = int(opt)
        print("Player Info: {}".format(lookup_player_id(player_id)))
    except ValueError:
        print("Player Info: {}".format(lookup_player(opt)))





