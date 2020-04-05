import pandas as pd
import numpy as np
import datetime

from csh_fantasy_bot import bot, nhl, roster_change_optimizer

import logging
logging.basicConfig(level=logging.INFO)

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

from elasticsearch import Elasticsearch
from elasticsearch import helpers

week_number = 19

es = Elasticsearch(hosts='http://localhost:9200', http_compress=True)

manager: bot.ManagerBot = bot.ManagerBot(week_number)
draft_results = manager.lg.draft_results()


#  add name, eligible positions, team

all_players_df = manager.all_players.loc[:,['name', 'eligible_positions','team_id','abbrev','player_id']]
all_players_df.set_index('player_id', inplace=True)

# draft_results = draft_results.merge(all_players_df, left_on='player_id', right_on='player_id')

pass

def filter_keys(document, columns):
    return {key: document[key] for key in columns}

draft_results_cols = ['pick']
def doc_generator_projections(df, draft_year, draft_date):
    for document in df:
        document['player_id'] = int(document['player_key'].split('.')[-1])
        document['draft_year'] = draft_year
        document['fantasy_team_id'] = int(document['team_key'].split('.')[-1])
        document['league_ID'] = int(document['team_key'].split('.')[2])
        document['timestamp'] = draft_date
        try:
            document['name'] = all_players_df.loc[document['player_id'],'name']
            document['abbrev'] = all_players_df.loc[document['player_id'], 'abbrev']
            document['eligible_positions'] = all_players_df.loc[document['player_id'], 'eligible_positions']
        except KeyError:
            print('no player id found in yahoo list: {}'.format(document['player_id']))
        yield {
            "_index": 'fantasy-bot-draft',
            "_type": "doc",
            "_id": "{}-{}".format(document['pick'], draft_year),
            "_source": document,
        }


helpers.bulk(es, doc_generator_projections(draft_results,2020,datetime.date(2019,9,27)))

pass
# draft_results