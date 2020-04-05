from datetime import date
import json
import time
import pandas as pd

from nhl_scraper.nhl import Scraper

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)


season_opening_date = date(2019,10,2)
season_end_date = date(2020,10,8)
nhl_scraper = Scraper()
games = nhl_scraper.games(season_opening_date, season_end_date)

for game in games:
    print('downloading boxscore, id={}'.format(game))
    box_score = nhl_scraper.box_scores(game,format='json')
    with open('box-scores/{}.json'.format(game), 'w') as outfile:
        json.dump(box_score, outfile)
    time.sleep(1)
pass