"""Export teams player results to ES."""
from datetime import date, timedelta, datetime
import time
import logging
import pandas as pd

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


def export_results(league_id, start_date=None,end_date=None):
    """Move player results to ES."""
    league = FantasyLeague(league_id)
    posns = league.positions()
    roster_spots = list()
    for posn in posns:
        for index in range(posns[posn]['count']):
            roster_spots.append(f"{posn}{index +1}")

    # TODO excluding goalie stats for now
    player_stats = [stat['display_name'] for stat in league.stat_categories() if stat['position_type'] == 'P']
    # Weighting for valuing results for each player stat
    weights_series = pd.Series([1, 1, .5, .5, 1, .1, .7], index=player_stats)

    all_players_df = league.all_players()
    all_players_df.set_index('player_id', inplace=True)
    es = Elasticsearch(hosts=ELASTIC_URL, http_compress=True)
    
    """Will load and return the prediction builder."""
    def loader():
        return fantasysp_scrape.Parser()

    expiry = timedelta(minutes=300 * 24 * 60)
    # TODO need to be able to pull predictions as-of
    pred_bldr = team_caching.load_prediction_builder(expiry, loader)
    projections = all_players_df[all_players_df.position_type == 'P']
    projections.reset_index(inplace=True)
    projections = pred_bldr.predict(projections)

    season_start_date = datetime.strptime(league.settings()['start_date'], '%Y-%m-%d').date()
    season_end_date = datetime.strptime(league.settings()['end_date'], '%Y-%m-%d').date()
    for team_dict in league.teams():
        fantasy_team_id = int(team_dict['team_key'].split('.')[-1])
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
            actual_stats.loc[actual_stats["G"] != '-' , 'fpts'] = actual_stats[actual_stats["G"] != '-' ][player_stats].mul(weights_series).sum(1)

            # we will create another set of stats 'fantasy_' which will be actual 
            # if player was on active roster for the day, otherwise stats will be 0
            fantasy_stats = actual_stats.copy()
            fantasy_stats.loc[daily_roster['selected_position'] == 'BN',:] = 0
            daily_stats = actual_stats.join(fantasy_stats, lsuffix='_actual', rsuffix='_fantasy')
            projected_stats = projections.loc[daily_stats.index,player_stats]
            projected_stats.loc[projected_stats.G == projected_stats.G, 'fpts'] = projected_stats.mul(weights_series).sum(1)
            daily_stats = daily_stats.join(projected_stats.add_suffix('_projected'))
            daily_stats = daily_stats.join(daily_roster.loc[:,['name', 'selected_position', 'eligible_positions', 'status','roster_position']])
            daily_stats['game_date'] = play_date
        
            team_stats = team_stats.append(daily_stats)
            play_date += timedelta(days=1)
            # So we don't get rate limited by Yahoo
            time.sleep(2)
        
        team_stats.loc[:, 'fantasy_team_id'] = fantasy_team_id
        team_stats.loc[:, 'fantasy_team_name'] = team_dict['name']
        team_stats.replace({'-': -555}, inplace=True)
        team_stats.fillna(-555,inplace=True)
        team_stats.replace({-555: None}, inplace=True)
        

        helpers.bulk(es, doc_generator_team_results(team_stats, team_stats.columns.tolist()))
    
    log.debug("finished export of player results")