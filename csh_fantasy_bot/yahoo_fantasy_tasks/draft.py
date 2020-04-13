"""Write draft results to ES."""
import datetime
from elasticsearch import Elasticsearch
from elasticsearch import helpers

from csh_fantasy_bot.yahoo_fantasy_tasks import oauth_token
from csh_fantasy_bot.league import FantasyLeague
from csh_fantasy_bot.config import ELASTIC_URL



def export_draft_es(league_id):
    """Read draft results for league, write to ES."""
    league = FantasyLeague(oauth_token,league_id)
    all_players_df = league.all_players()
    all_players_df.set_index('player_id', inplace=True)
    teams = league.teams()
    draft_results = league.draft_results()
    print(f"Number of players drafted {len(draft_results)}")
    es = Elasticsearch(hosts=ELASTIC_URL, http_compress=True)
    def doc_generator_projections(df, draft_year, draft_date):
        for document in df:
            document['player_id'] = int(document['player_key'].split('.')[-1])
            document['draft_year'] = draft_year
            document['fantasy_team_id'] = int(document['team_key'].split('.')[-1])
            document['team_name'] = teams[document['fantasy_team_id'] - 1]['name']
            document['league_ID'] = int(document['team_key'].split('.')[2])
            document['timestamp'] = draft_date
            try:
                document['name'] = all_players_df.loc[document['player_id'],'name']
                document['abbrev'] = all_players_df.loc[document['player_id'], 'abbrev']
                document['eligible_positions'] = all_players_df.loc[document['player_id'], 'eligible_positions']
            except KeyError as e:
                print('no player id found in yahoo list: {}'.format(document['player_id']))
            yield {
                "_index": 'fantasy-bot-draft',
                "_type": "doc",
                "_id": "{}-{}".format(document['pick'], draft_year),
                "_source": document,
            }


    helpers.bulk(es, doc_generator_projections(draft_results,2020,datetime.date(2019,9,27)))
    