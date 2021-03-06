import os
import time
import datetime
from datetime import date, timedelta
import pandas as pd
import numpy as np

from elasticsearch import Elasticsearch
from elasticsearch import helpers

from elasticsearch_dsl import Document, Date, Nested, Boolean, \
    analyzer, InnerDoc, Completion, Keyword, Text, Float, Short

from yahoo_fantasy_api import league,team
from csh_fantasy_bot import bot
from csh_fantasy_bot.config import ELASTIC_URL

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

if 'YAHOO_OAUTH_FILE' in os.environ:
    oauth_file = os.environ['YAHOO_OAUTH_FILE']
else:
    oauth_file = 'oauth2.json'

es = Elasticsearch(hosts=ELASTIC_URL, http_compress=True)

league_id = '396.l.53432'
league_id = "403.l.18782"

manager = bot.ManagerBot(1,league_id=league_id)
lg = manager.lg
sc = lg.sc

teams = lg.teams()
roster_positions = lg.positions()
all_players = manager.all_players
# player_stats = manager.stat_categories
# weights_series = pd.Series([1, 1, .5, .5, 1, .1, .7], index=player_stats)
projected_player_stats = ['proj_{}'.format(stat) for stat in manager.stat_categories]
# player_projection_columns =['name','eligible_positions','team_id','team_name','game_date','player_id'] + player_stats


def filter_keys(document, columns):
    return {key: document[key] for key in columns}


def doc_generator_team_results(df, columns):
    df_iter = df.iterrows()
    for index, document in df_iter:
        yield {
            "_index": 'fantasy-bot-player-results',
            "_type": "_doc",
            "_id": "{}.{}.{}".format(document['fantasy_team_id'], document['game_date'],index),
            "_source": filter_keys(document, columns),
        }


projections = manager.all_players[manager.all_players.position_type == 'P']
projections.reset_index(inplace=True)
projections = manager.pred_bldr.predict(projections)
projections.reset_index(inplace=True)
projections = projections.add_prefix('proj_')
projections.rename(columns={"proj_player_id": "player_id"}, inplace=True)
# projections.replace(np.nan, '-', inplace=True)

# avail_players.loc[:,'fpts'] = avail_players[self.player_stats].mul(self.weights_series).sum(1)
for team_dict in teams:
    # oct 2 hard code start season
    # end mar 12
    fantasy_team_id = int(team_dict['team_key'].split('.')[-1])
    if fantasy_team_id > 0:
        the_team = team.Team(sc, team_dict['team_key'])
        team_stats = pd.DataFrame()
        play_date = datetime.datetime.strptime(lg.settings()['start_date'], '%Y-%m-%d') 
        end_date = datetime.datetime.strptime(lg.settings()['end_date'], '%Y-%m-%d')  
        while play_date < end_date:
            print(f"Processing {team_dict['team_key']}, date: {play_date}")
            the_roster = the_team.roster(day=play_date)
            time.sleep(2)
            daily_roster = pd.DataFrame(the_roster)
            lineup = daily_roster.query('position_type != "G"')
            stats = lg.player_stats(lineup.player_id.tolist(), "date", date=play_date)
            daily_stats = pd.DataFrame(stats).loc[:, ['player_id'] + manager.stat_categories]
            # daily_stats.loc[daily_stats["G"] != '-' , 'fpts'] = daily_stats[daily_stats["G"] != '-' ][player_stats].mul(weights_series).sum(1)
            daily_stats = daily_stats.add_prefix('actual_')
            daily_stats.rename(columns={"actual_player_id": "player_id"}, inplace=True)
            daily_stats = daily_stats.merge(daily_roster.loc[:, ['name', 'selected_position', 'player_id', 'eligible_positions', 'status']],
                                          left_on='player_id', right_on='player_id')
            daily_stats = daily_stats.merge(
                projections.loc[:, ['player_id'] + projected_player_stats],
                left_on='player_id', right_on='player_id')
            daily_stats['game_date'] = play_date
            daily_stats['timestamp'] = play_date
            daily_stats['league_id'] = league_id
            # daily_stats.replace('-', np.nan, inplace=True)
            # nan is never == nan, so remove players who did not play for date
            # daily_stats.query('G == G')
            team_stats = team_stats.append(daily_stats)
            play_date += timedelta(days=1)
        team_stats.loc[:, 'fantasy_team_id'] = fantasy_team_id
        team_stats.loc[:, 'fantasy_team_name'] = team_dict['name']
        # team_stats['score_type'] = 'a'
        # team_stats.drop(columns=['score_type'], inplace=True)
        # team_stats.replace('-', None, inplace=True)
        # team_stats = team_stats.fillna('-')
        team_stats.replace({'-': -555}, inplace=True)
        team_stats.fillna(-555,inplace=True)
        team_stats.replace({-555: None}, inplace=True)
        helpers.bulk(es, doc_generator_team_results(team_stats, team_stats.columns.tolist()))


