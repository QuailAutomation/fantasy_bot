import datetime
import pandas as pd
import json
from nhl_scraper.nhl import Scraper

from elasticsearch import Elasticsearch
from elasticsearch import helpers

es = Elasticsearch(hosts='http://localhost:9200', http_compress=True)

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

nhl = Scraper()

a_day = datetime.date(2019,10,4)
end_day = datetime.date(2020,4,14)
games = nhl.linescores(a_day, end_day)


def doc_generator_linescores(games):
    for game in games:
        game['timestamp'] = game['gameDate']
        # document['player_id'] = index
        yield {
            "_index": 'fantasy-nhl-line-scores-2019',
            "_type": "_doc",
            "_id": game['gamePk'],
            "_source": game,
        }


helpers.bulk(es, doc_generator_linescores(games))
pass


