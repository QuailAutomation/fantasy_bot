import pandas as pd
import numpy as np
from datetime import datetime, timezone, date

from csh_fantasy_bot import bot, nhl, roster_change_optimizer

import logging
logging.basicConfig(level=logging.INFO)

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

from elasticsearch import Elasticsearch
from elasticsearch import helpers

es = Elasticsearch(hosts='http://localhost:9200', http_compress=True)

stats = ['G','A','SOG','+/-','HIT','PIM','FW']
weights_series = pd.Series([1, .75, 1, .5, 1, .1, 1], index=stats)

week_number = 1
manager = bot.ManagerBot(week_number)

projections = manager.all_players[manager.all_players.position_type == 'P']
projections.reset_index(inplace=True)

projections = manager.pred_bldr.predict(projections)
projection_date = date(2020,3,8)
projections.loc[:, 'projection_date'] = projection_date
projections['timestamp'] = projection_date
player_projection_columns =['name','eligible_positions','team_id','team_name','projection_date','player_id','timestamp'] + stats


def filter_keys(document, columns):
    return {key: document[key] for key in columns}


def doc_generator_projections(df):
    df_iter = df.iterrows()
    for index, document in df_iter:
        try:
            document['player_id'] = int(index)
            if not np.isnan(document['G']):
                yield {
                    "_index": 'fantasy-bot-player-projections',
                    "_type": "_doc",
                    "_id": "{}.{}".format(index,projection_date),
                    "_source": filter_keys(document,player_projection_columns),
                }
        except Exception as e:
            print(e)
            pass


helpers.bulk(es, doc_generator_projections(projections))