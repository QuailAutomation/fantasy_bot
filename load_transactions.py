import os
import json
from datetime import datetime

from elasticsearch import Elasticsearch

from yahoo_oauth import OAuth2
from yahoo_fantasy_api import League

import logging
logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

import redis

# r = redis.StrictRedis(host='localhost', port=6379, db=0)
# r.set('foo', 'bar')
# print('value "foo" from Redis: {}'.format(r.get('foo')))

from elasticsearch_dsl import Document, Date, Nested, Boolean, \
    analyzer, InnerDoc, Completion, Keyword, Text, Search


class RosterMove(InnerDoc):
    player_id = Text()
    player_name = Text(fields={'raw': Keyword()})
    transaction_type = Text()


class LeagueTransaction(Document):
    key = Text()
    timestamp = Date()
    status = Text()
    roster_moves = Nested(RosterMove,include_in_parent=True)

    # comments = Nested(Comment)

    class Index:
        name = 'fantasy-bot-league-transactions'

    def add_roster_move(self, player_id, name, move_type):
        self.roster_moves.append(
            RosterMove(player_id=player_id, player_name=name, transaction_type=move_type))
        pass


oauth = OAuth2(None, None, from_file='oauth2.json')
league: League = League(oauth,'396.l.53432')

transactions = league.transactions()
transactions.reverse()
es_url = os.environ.get('ELASTIC_URL', 'http://localhost:9200')

from elasticsearch_dsl import connections

connections.create_connection(hosts=['localhost'], timeout=20)

LeagueTransaction.init()
if True:
    for trans in zip(transactions[1::2], transactions[0::2]):
        # if k['type'] not in ['commish']:
        #     print(k)
        #     print(i)
        dt_object = datetime.fromtimestamp(int(trans[0]['timestamp']))
        trans[0]['timestamp'] = dt_object
        id = int(trans[0]['transaction_id'])
        string_rep = json.dumps(trans[0],default=str)
        esTrans = LeagueTransaction(_id=trans[0]['transaction_key'], id=id,timestamp=dt_object,status=trans[0]['status'],type=trans[0]['type'])

        if len(trans[1]) > 0:
            for move in trans[1]['players'].values():
                print("roster move: {}".format(move))
                if type(move) is dict:
                    try:
                        try:
                            player_id = move['player'][0][1]['player_id']
                        except TypeError as e:
                            print(e)
                        name = move['player'][0][2]['name']['full']
                        # yahoo sometimes uses a list, sometimes doesn't so lets check.
                        txn_data = move['player'][1]['transaction_data']
                        if type(txn_data) is list:
                            txn_data = txn_data[0]

                        move_type = txn_data['type']
                    except KeyError as e:
                        print(e)
                    esTrans.add_roster_move(player_id, name, move_type)

        esTrans.save()
        pass

        # res = es.index(index="fantasy-bot-league-transactions", id=trans[0]['transaction_key'], doc_type="_doc", body=string_rep)
    pass

# s = Search(index='fantasy-bot-league-transactions').sort('-id')
# response = s.execute()
# if len(response.hits) > 0:
#     max_id = response.hits[0].id
#     print(max_id)


