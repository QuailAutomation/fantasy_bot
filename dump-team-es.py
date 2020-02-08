import pandas as pd
from elasticsearch import Elasticsearch
from elasticsearch import helpers

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

weekly_results = pd.read_csv('team-results.csv')
print(weekly_results.shape)
print(weekly_results.head(40))

es = Elasticsearch(hosts='http://192.168.1.20:9200', http_compress=True)

# use_these_keys = ['player_id','play_date', 'G', 'A','+/-','PIM','SOG','FW','HIT','score_type']
use_these_keys = weekly_results.columns
def filterKeys(document):
    return {key: document[key] for key in use_these_keys}

def doc_generator(df):
    df_iter = df.iterrows()
    for index, document in df_iter:
        yield {
            "_index": 'fantasy-bot-team-results',
            "_type": "_doc",
            "_id": "{}-{}-{}".format(document['player_id'],document['play_date'],document['score_type']),
            "_source": filterKeys(document),
        }


helpers.bulk(es, doc_generator(weekly_results))