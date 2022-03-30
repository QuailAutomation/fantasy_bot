import pandas as pd
import numpy as np
import datetime
import time
import json
import objectpath

from csh_fantasy_bot import bot, nhl, roster_change_optimizer
from yahoo_fantasy_api import yhandler

import logging
logging.basicConfig(level=logging.INFO)

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

from elasticsearch import Elasticsearch
from elasticsearch import helpers


es = Elasticsearch(hosts='http://192.168.1.20:9200', http_compress=True)

# league_id = "403.l.18782"
league_id = "411.l.85094"

manager: bot.ManagerBot = bot.ManagerBot(league_id=league_id)


class JsonLoggingYHandler(yhandler.YHandler):

    def __init__(self, sc):
        super().__init__(sc)
        self.num_players_picked = -1

    def get_draft_results(self, league_id):
        raw = super().get_draft_results(league_id)
        t = objectpath.Tree(raw)
        elems = t.execute('$..draft_result')
        num_drafted = 0
        for ele in elems:
            if 'player_key' in ele.keys():
                num_drafted += 1
            else:
                break
        
        if num_drafted > self.num_players_picked:
            # write out json
            with open(f'./draft_json-{league_id}/pick-{num_drafted}.json', 'w') as json_file:
                json.dump(raw, json_file)
            self.num_players_picked = num_drafted

        return raw

# let's write json out to files
# manager.lg.inject_yhandler(JsonLoggingYHandler(manager.lg.sc))
print("here")


def load_draft():
    draft_results = manager.lg.draft_results()

    print(f"Num players drafted: {len(draft_results)}")
    #  add name, eligible positions, team
    if len(draft_results) > 0:
        all_players_df = manager.lg._all_players().loc[:,['name', 'eligible_positions','team_id','team_abbr']]
        all_players_df = manager.lg._all_players()
        all_players_df.set_index('player_id', inplace=True)

        # draft_results = draft_results.merge(all_players_df, left_on='player_id', right_on='player_id')

        pass

        def doc_generator_projections(df, draft_date):
            league_season = int(manager.lg.settings()['season'])
            for document in df:
                document['player_id'] = int(document['player_key'].split('.')[-1])
                document['draft_year'] = league_season
                document['fantasy_team_id'] = int(document['team_key'].split('.')[-1])
                document['league_ID'] = int(document['team_key'].split('.')[2])
                document['timestamp'] = draft_date
                document['league_id'] = league_id
                try:
                    document['name'] = all_players_df.loc[document['player_id'],'name']
                    document['abbrev'] = all_players_df.loc[document['player_id'], 'abbrev']
                    document['eligible_positions'] = all_players_df.loc[document['player_id'], 'eligible_positions']
                except KeyError:
                    print('no player id found in yahoo list: {}'.format(document['player_id']))
                yield {
                    "_index": f'fantasy-nhl-{manager.lg.settings()["season"]}-draft',
                    "_type": "doc",
                    "_id": f"{league_id}-{league_season}-{document['pick']}",
                    "_source": document,
                }


        helpers.bulk(es, doc_generator_projections(draft_results, datetime.datetime.fromtimestamp(int(manager.lg.settings()['draft_time']))))

if __name__ == "__main__":
    load_draft()
    # change to true for real-time results (ie during draft)
    real_time = False
    while real_time:
        print("Sleeping")
        time.sleep(2)
        load_draft()
    