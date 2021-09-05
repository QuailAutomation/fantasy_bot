from datetime import datetime

from csh_fantasy_bot.projections.yahoo_nfl import generate_predictions, PredictionType, retrieve_draft_order
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa


oauth = OAuth2(None, None, from_file='oauth2.json')

gm = yfa.Game(oauth, 'nfl')
ids = gm.league_ids(year=2020)

lg = gm.to_league(ids[0])
lg.draft_results()
draft_order = retrieve_draft_order(lg)
print(draft_order)

predictions = generate_predictions(lg,predition_type=PredictionType.rest_season)
# predictions.to_csv("2021-mdgc-predictions.csv", index=False)


# import pandas as pd
# df = pd.read_csv("2021-mdgc-predictions.csv")
# print(df.head())

