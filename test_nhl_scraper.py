from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
from csh_fantasy_bot.yahoo_scraping import generate_predictions, PredictionType

oauth = OAuth2(None, None, from_file='oauth2.json')

f_year = 2021
gm = yfa.Game(oauth, 'nhl')
ids = gm.league_ids(year=f_year)

lg = gm.to_league(ids[0])
league_id = lg.league_id
print(lg)

projections = generate_predictions(lg.league_id, predition_type=PredictionType.rest_season)
print(projections.head())


yahoo_prediction_fname = f"./.cache/gui_draft/{league_id}-yahoo-predictions.csv"

projections.to_csv(yahoo_prediction_fname, index=True)
print(f'Wrote file: {yahoo_prediction_fname}')
