from datetime import datetime

import pandas as pd 
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa



oauth = OAuth2(None, None, from_file='oauth2.json')

f_year = 2021
gm = yfa.Game(oauth, 'nfl')
ids = gm.league_ids(year=f_year)

lg = gm.to_league(ids[1])

ab = lg.player_details("Antonio Brown")
print(ab)