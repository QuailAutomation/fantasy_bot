import datetime
import pandas as pd
import json
import os

from nhl_scraper.nhl import Scraper
from csh_fantasy_bot import bot

from elasticsearch import Elasticsearch
from elasticsearch import helpers

es = Elasticsearch(hosts='http://192.168.1.20:9200', http_compress=True)

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)


    
def dump_predictions(league_id):
    manager = bot.ManagerBot(league_id=league_id)

    predictions = pd.read_csv(prediction_csv,
                        converters={"eligible_positions": lambda x: x.strip("[]").replace("'", "").split(", ")})
    predictions['league_id'] = league_id
    predictions.rename(columns={"id": "player_id"}, inplace=True)
    predictions.set_index('player_id', inplace=True)

    scored_categories = manager.lg.scoring_categories() # ["G", "A", "+/-", "PIM", "SOG", "FW", "HIT"]
    d_scored_categories = scored_categories.copy()
    # if FW are in cats, let's ignore them for D.  Keeps D fantasy score close relative to F 
    try:
        d_scored_categories.remove('FW')
    except ValueError:
        pass
    # d_scored_categories = ["G", "A", "+/-", "PIM", "SOG", "HIT"]
    es_colums = ["name", "position","team","preseason_rank","current_rank","fantasy_score","GP", "csh_rank", "league_id", "player_id"]
    def produce_csh_ranking(predictions, scoring_categories, selector):
        """Create ranking by summing standard deviation of each stat, summing, then dividing by num stats."""
        f_mean = predictions.loc[selector,scoring_categories].mean()
        f_std =predictions.loc[selector,scoring_categories].std()
        f_std_performance = (predictions.loc[selector,scoring_categories] - f_mean)/f_std
        for stat in scoring_categories:
            predictions.loc[selector, stat + '_std'] = (predictions[stat] - f_mean[stat])/f_std[stat]
        # predictions = predictions.join(f_std_performance, how='left', rsuffix='_std')
        predictions.loc[selector, 'fantasy_score'] = f_std_performance.sum(axis=1)/len(scoring_categories)
        # predictions.sort_values('fantasy_score', inplace=True,ascending=False)
        # sorted_predictions = predictions.reset_index().sort_values('fantasy_score', ascending=False, ignore_index=True)
        # sorted_predictions['csh_rank'] = sorted_predictions.index + 1
        return predictions
    # the bulk importer for ES can't handled NAN, so let's initialize to 0
    for stat in scored_categories:
            predictions.loc[:, stat + '_std'] = 0
    produce_csh_ranking(predictions, scored_categories, predictions['position'] != 'D')
    produce_csh_ranking(predictions, d_scored_categories, predictions['position'] == 'D')
    # predictions.sort_values('fantasy_score', inplace=True,ascending=False)
    sorted_predictions = predictions.reset_index().sort_values('fantasy_score', ascending=False, ignore_index=True)
    sorted_predictions['csh_rank'] = sorted_predictions.index + 1
    print(sorted_predictions.head(20))

    def filter_keys(document, columns):
        """Return dict as specified by colums list."""
        return {key: document[key] for key in columns}

    def doc_generator_linescores(player_predictions, categories):
        df_iter = player_predictions.iterrows()
        for index, player_prediction in df_iter:
            # game['timestamp'] = game['gameDate']
            # document['player_id'] = index
            yield {
                "_index": 'fantasy-nhl-preseason-predictions-2021',
                "_type": "_doc",
                "_id": f"{player_prediction['league_id']}-{player_prediction['player_id']}",
                "_source": filter_keys(player_prediction, categories + 
                                    [cat + "_std" for cat in categories] + 
                                    es_colums),
            }


    helpers.bulk(es, doc_generator_linescores(sorted_predictions, scored_categories))
    # helpers.bulk(es, doc_generator_linescores(ordinal_d_predictions, d_scored_categories))
    pass


if __name__ == "__main__":
    league_id = "403.l.18782"
    league_id = "403.l.41177"

    prediction_csv = f'.cache/{league_id}/yahoo-projections-stats.csv'
    if os.path.exists(prediction_csv):
        dump_predictions(league_id)
    else:
        print(f"Prediction file does not exist: {prediction_csv}")
    