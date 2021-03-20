"""Export teams player results to ES."""
from csh_fantasy_bot.bot import ManagerBot
import datetime
import logging
import pandas as pd
import time
from elasticsearch import Elasticsearch
from elasticsearch import helpers

from yahoo_fantasy_api import team
from csh_fantasy_bot.league import FantasyLeague
from csh_fantasy_bot.config import ELASTIC_URL
from csh_fantasy_bot import utils, fantasysp_scrape

log = logging.getLogger(__name__)

# TODO this is hardcoded
# predictions should be in the league cache, they are
# not team specific now
team_caching = utils.TeamCache("396.l.53432.t.2")


def filter_keys(document, columns):
    """Return subset of dict, defined by columns."""
    return {key: document[key] for key in columns}


def doc_generator_team_results(df, columns):
    """Generate record to be exported to ES."""
    for index, document in df.iterrows():
        yield {
            "_index": 'fantasy-bot-player-results',
            "_type": "_doc",
            "_id": "{}.{}.{}".format(document['fantasy_team_id'], document['game_date'], index),
            "_source": filter_keys(document, columns),
        }


def export_results(league_id, start_date, end_date):
    """Move player results to ES."""
    start_date = datetime.date(2021,3,15)
    end_date = datetime.date(2021,3,21)
    manager = ManagerBot(league_id)
    league = manager.lg
    posns = league.positions()
    # C1, C2, LW1, etc...
    roster_spots = [f'{position}{i+1}' for position,count in league.roster_makeup().items() for i in range(count) ]
    # TODO excluding goalie stats for now
    player_stats = league.scoring_categories()

    all_players_df = league._all_players()
    all_players_df.set_index('player_id', inplace=True)
    es = Elasticsearch(hosts=ELASTIC_URL, http_compress=True)
    
    projections = all_players_df[all_players_df.position_type == 'P']
    # projections.reset_index(inplace=True)
    projections = manager.pred_bldr.predict(projections)

    season_start_date = datetime.datetime.strptime(league.settings()['start_date'], '%Y-%m-%d').date()
    season_end_date = datetime.datetime.strptime(league.settings()['end_date'], '%Y-%m-%d').date()

    for team_dict in league.teams():
        fantasy_team_id = int(team_dict['team_key'].split('.')[-1])
        
        if fantasy_team_id != 2: continue

        the_team = league.team_by_key(team_dict['team_key'])
        team_stats = pd.DataFrame()
        #  if start_date is None else start_date
        play_date = start_date or season_start_date
        stop_date = end_date or season_end_date
        while play_date < stop_date:
            log.debug(f"Processing {team_dict['team_key']}, date: {play_date}")
            daily_roster = pd.DataFrame(the_team.roster(day=play_date))
            daily_roster['roster_position'] = daily_roster.index
            daily_roster.set_index('player_id', inplace=True)
            lineup = daily_roster.query('position_type != "G"')
            actual_stats = pd.DataFrame(league.player_stats(lineup.index.tolist(), "date", date=play_date)).loc[:, ['player_id'] + player_stats]
            actual_stats.set_index('player_id', inplace=True)
            # TODO do we want fpts back in?
            # actual_stats.loc[actual_stats["G"] != '-' , 'fpts'] = actual_stats[actual_stats["G"] != '-' ][player_stats].mul(weights_series).sum(1)

            # we will create another set of stats 'fantasy_' which will be actual 
            # if player was on active roster for the day, otherwise stats will be 0
            fantasy_stats = actual_stats.copy()
            fantasy_stats.loc[daily_roster['selected_position'] == 'BN',:] = 0
            daily_stats = actual_stats.join(fantasy_stats, lsuffix='_actual', rsuffix='_fantasy')
            projected_stats = projections.loc[daily_stats.index,player_stats]
            # projected_stats.loc[projected_stats.G == projected_stats.G, 'fpts'] = projected_stats.mul(weights_series).sum(1)
            daily_stats = daily_stats.join(projected_stats.add_suffix('_projected'))
            daily_stats = daily_stats.join(daily_roster.loc[:,['name', 'selected_position', 'eligible_positions', 'status','roster_position']])
            # ES uses UTC, use end of day PST
            daily_stats['game_date'] = datetime.datetime.combine(play_date, datetime.time.max)
        
            team_stats = team_stats.append(daily_stats)
            play_date += datetime.timedelta(days=1)
            # So we don't get rate limited by Yahoo
            time.sleep(1)
        
        team_stats.loc[:, 'fantasy_team_id'] = fantasy_team_id
        team_stats.loc[:, 'fantasy_team_name'] = team_dict['name']
        team_stats.replace({'-': -555}, inplace=True)
        team_stats.fillna(-555,inplace=True)
        team_stats.replace({-555: None}, inplace=True)
        

        helpers.bulk(es, doc_generator_team_results(team_stats, team_stats.columns.tolist()))
    
    log.debug("finished export of player results")