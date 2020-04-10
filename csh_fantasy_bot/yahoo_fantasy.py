import logging
from datetime import datetime
import json

from elasticsearch import RequestError
from elasticsearch_dsl import connections

from csh_fantasy_bot.config import ELASTIC_URL
connections.create_connection(hosts=[ELASTIC_URL], timeout=20)

es_logger = logging.getLogger('elasticsearch')
es_logger.setLevel(logging.WARNING)

from elasticsearch_dsl import Document, Date, Nested, Boolean, \
    analyzer, InnerDoc, Completion, Keyword, Text, Search

def _get_last_processed_roster_change_id():
    ''' read from es to find id of last league transaction'''
    last_id = 0
    try:
        s = Search(index='fantasy-bot-league-transactions').sort('-id')
        response = s.execute()
        if len(response.hits) > 0:
            max_id = response.hits[0].id
            return max_id
    except RequestError as e:
        logging.error(e)
    return last_id


def check_for_new_changes(league, write_new=True):
    """Check if there have been roster moves since last check."""
    found_new_transactions = False
    last_processed_id = _get_last_processed_roster_change_id()

    transactions = league.transactions()
    transactions.reverse()

    for trans in zip(transactions[1::2], transactions[0::2]):
        dt_object = datetime.fromtimestamp(int(trans[0]['timestamp']))
        trans[0]['timestamp'] = dt_object
        id = int(trans[0]['transaction_id'])
        if id > last_processed_id:
            found_new_transactions = True
            if write_new:
                esTrans = LeagueTransaction(_id=trans[0]['transaction_key'], id=id, timestamp=dt_object,
                                            status=trans[0]['status'], type=trans[0]['type'])
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
    return found_new_transactions


class RosterMove(InnerDoc):
    player_id = Text()
    player_name = Text(fields={'raw': Keyword()})
    transaction_type = Text()


class LeagueTransaction(Document):
    key = Text()
    timestamp = Date()
    status = Text()
    roster_moves = Nested(RosterMove)

    # comments = Nested(Comment)

    class Index:
        name = 'fantasy-bot-league-transactions'

    def add_roster_move(self, player_id, name, move_type):
        self.roster_moves.append(
            RosterMove(player_id=player_id, player_name=name, transaction_type=move_type))
        pass


LeagueTransaction.init()

