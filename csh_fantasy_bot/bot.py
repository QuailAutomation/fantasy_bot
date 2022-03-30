#!/bin/python
from calendar import week
import logging
import pickle
import os
from dotenv import load_dotenv
from enum import Enum
from collections import namedtuple
from datetime import datetime, timedelta, date
from collections import defaultdict
from typing import ClassVar 
import pandas as pd
import numpy as np
import importlib
from pandas.core.frame import DataFrame
from pandas.core.indexes.datetimes import date_range


import yahoo_fantasy_api as yfa
from nhl_scraper.nhl import Scraper 
from csh_fantasy_bot import utils, yahoo_scraping
from csh_fantasy_bot.league import FantasyLeague
from csh_fantasy_bot.nhl import score_team
from csh_fantasy_bot.yahoo_projections import retrieve_yahoo_rest_of_season_projections, produce_csh_ranking

from csh_fantasy_bot.scoring import ScoreComparer

# load dotenv
load_dotenv()
default_league_id = os.getenv('default_league_id',default=None)

LOG = logging.getLogger(__name__)

MissingRosterPlayer = namedtuple('MissingRosterPlayer', 'player_id name status')

class ScoringAlgorithm(Enum):
    milp = "score_opp" # S_PS7 or S_PSR
    fpts= "score_league"


class WS:
    @classmethod
    def last(cls, n_weeks):
        slice_posn = n_weeks * -1
        return slice(slice_posn - 1,-1)
    
    @classmethod
    def between(cls, start, end):
        return slice(start-1, end)

    current = slice(-2,-1)
    next = slice(-1,None)

# team selector
class TS(Enum):
    me = "me"
    opp = "opp"
    all = "all"

class TeamInfo:
    def __init__(self, key, game_week):
        self.key = key
        self.game_week : GameWeek  = game_week
    
    def scores(self):
        return self.game_week.score(team_key=self.key)
    
    def roster(self):
        return self.game_week.all_player_predictions[self.game_week.all_player_predictions.fantasy_status == int(self.key.split('.')[-1])]

class GameWeek:
    def __init__(self, manager, week, as_of) -> None:
        self.manager:ManagerBot = manager
        self.week_number = week
        self.simulation_mode = False
        self.as_of = as_of
        self.date_range = pd.date_range(*manager.lg.week_date_range(self.week_number))
        self._team_scores = None
        # assert as_of >= self.date_range[0]
        self._all_players = None
        self._roster_changes_made = None
        self._roster_changes_allowed = None
        self._all_player_predictions = None
        self._score_comparer = None
        self._opponent:TeamInfo = None

    @property 
    def all_players(self):
        if  self._all_players is None:
            self._all_players = self.manager.lg.as_of(self.as_of).all_players()
        return self._all_players
    @property
    def opponent(self) -> TeamInfo:
        if not self._opponent:
            opp_team_key = self.manager.tm.matchup(self.week_number)
            self._opponent = TeamInfo(opp_team_key, self)   
        return self._opponent 

    @property
    def score_comparer(self):
        if not self._score_comparer:
            self._score_comparer = ScoreComparer(self.team_scores.values(), self.manager.stat_categories)
            self._score_comparer.opp_sum = self.opponent.scores().sum()

        return self._score_comparer

    def override_opponent(self, opponent_id):
        self._opponent = TeamInfo(opponent_id, self)
    def fetch_league_lineups(self):
        scoring_results = {tm['team_key'].split('.')[-1]:self.manager.lg.score_team_fpts(self.all_player_predictions[self.all_player_predictions.fantasy_status == int(tm['team_key'].split('.')[-1])], \
                                    date_range=self.date_range, simulation_mode=self.simulation_mode, team_id=tm['team_key'])[1] 
                                for tm in self.lg.teams()}
        return scoring_results

    @property
    def all_player_predictions(self):
        try:
            if self._all_player_predictions == None:
                self._all_player_predictions = self.produce_all_player_predictions()
        except ValueError:
            pass
        return self._all_player_predictions

    @property
    def team_scores(self):
        if not self._team_scores:
            self._team_scores =  {tm['team_key'].split('.')[-1]:self.manager.lg.score_team_fpts(self.all_player_predictions[self.all_player_predictions.fantasy_status == int(tm['team_key'].split('.')[-1])], \
                                    date_range=self.date_range, simulation_mode=self.simulation_mode, team_id=tm['team_key'])[1] 
                                for tm in self.manager.lg.teams()}
        return self._team_scores

    def score(self, team_number=None, team_key=None, scoring_algo=ScoringAlgorithm.fpts):
        if team_key:
            team_number = team_key.split('.')[-1]
        if team_number:
            return self.team_scores[team_number]
        else:    
            return self._team_scores
    
    def produce_all_player_predictions(self):
        all_projections = self.manager.pred_bldr.predict(self.all_players)

        players_no_projections_on_team = all_projections[(all_projections.G != all_projections.G) \
                    & (all_projections.fantasy_status != 'FA') \
                    & (all_projections.position_type != 'G')    ].index

        # let's see if we rostered a player without projections.  if so we'll fall back on yahoo
        # retrieve_yahoo_rest_of_season_projections(self.league_id).loc[roster_results[roster_results.G != roster_results.G].index.values]
        if len(players_no_projections_on_team) > 0:
            yahoo_projections = retrieve_yahoo_rest_of_season_projections(self.manager.lg.league_id)
            yahoo_projections[self.manager.stat_categories] = yahoo_projections[self.manager.stat_categories].div(yahoo_projections.GP, axis=0)
            for player_id in players_no_projections_on_team.values:
                try:
                    all_projections.update(yahoo_projections.loc[[player_id]]) 
                except KeyError:
                    print(f"Could not find projection for {all_projections.loc[player_id]}")
        all_projections = all_projections.round(2)
        produce_csh_ranking(all_projections, self.manager.stat_categories, 
                    all_projections.index, ranking_column_name='fpts')

        #TODO this can be removed with support for goalies
        return all_projections[(all_projections.position_type == 'P')]
    
    def _get_num_roster_changes_made(self):
        # if the game week is in the future then we couldn't have already made changes
        if date.today() < self.date_range[0]:
            return 0

        def retrieve_attribute_from_team_info(team_info, attribute):
            for attr in team_info:
                if attribute in attr:
                    return attr[attribute]

        raw_matchups = self.manager.lg.matchups()
        team_id = self.manager.tm.team_key.split('.')[-1]
        num_matchups = raw_matchups['fantasy_content']['league'][1]['scoreboard']['0']['matchups']['count']
        for matchup_index in range(0, num_matchups):
            matchup = raw_matchups['fantasy_content']['league'][1]['scoreboard']['0']['matchups'][str(matchup_index)]
            for i in range(0, 2):
                try:
                    if retrieve_attribute_from_team_info(matchup['matchup']['0']['teams'][str(i)]['team'][0],
                                                         'team_id') == team_id:
                        return int(
                            retrieve_attribute_from_team_info(matchup['matchup']['0']['teams'][str(i)]['team'][0],
                                                              'roster_adds')['value'])
                except TypeError as e:
                    pass
        #TODO should check if playoffs
        plug_value = 0
        print("returning {} for roster changes, as no matchup found".format(plug_value))
        return plug_value
        assert False, 'Did not find roster changes for team'

    
    
    def compare_roster_yahoo_ideal(self, day=None):
        results = []
        roster_positions = self.manager.lg.roster_makeup(position_type='P').keys()
        opponent_key = self.manager.tm.matchup(self.week_number)
        opponent_scores = self.score(team_key=opponent_key)
        scores = self.manager.score_team(date_range=self.date_range,opponent_scores=opponent_scores.sum())
        todays_roster = scores[1].loc[(day,slice(None))].merge(self.all_players, left_index=True, right_on='player_id')[['name','rostered_position']]
        yahoo_roster = pd.DataFrame.from_dict(self.manager.tm.roster(day=day))
        yahoo_scoring_players = yahoo_roster[yahoo_roster.selected_position.isin(roster_positions)].set_index('player_id')
        missing_player_ids = todays_roster.index.difference(yahoo_scoring_players.index)
        
        league_name = self.manager.lg.settings()['name']
        if len(missing_player_ids) > 0:
            results.append(f"League: {league_name} - Players missing from projected ideal.")
            for player_id in missing_player_ids:
                results.append(MissingRosterPlayer(player_id,*self.all_players.loc[player_id,['name', 'status']].values))
        else:
            results.append(f'League: {league_name} - Yahoo roster matches projected ideal')    
        return results

    def _fetch_player_pool(self):
        """Build the roster pool of players."""
        if self.ppool is None:
            my_team_id = int(self.manager.tm.team_key.split('.')[-1])
            if self.simulation_mode:
                all_players = self.all_players
                
                my_roster = all_players[all_players.fantasy_status.isin([my_team_id, 'FA'])]
                my_roster.reset_index(inplace=True)
            else:
                current_lineup = self.lg.team_by_id(my_team_id)
                my_roster = current_lineup.append(self.fetch_waivers()).append(self.fetch_free_agents())

            players = self.pred_bldr.predict(my_roster)
            # let's double check for players on my roster who don't have current projections.  We will create our own by using this season's stats
            ids_no_stats = list(players.query(f'fantasy_status == {my_team_id} & G != G & position_type == "P" & status != "IR" ').index.values)
            the_stats = self.lg.player_stats(ids_no_stats,'season')
            
            for player_w_stats in the_stats:
                # a_player = players[players.player_id == player_w_stats['player_id']]
                for stat in self.stat_categories:
                    if player_w_stats['GP'] != '-' and player_w_stats['GP'] > 0:
                        players.loc[player_w_stats['player_id'], [stat]] = player_w_stats[stat] / player_w_stats['GP']

            self.ppool = players.query('~(G != G & position_type == "P" )')
            pass


class ManagerBot:
    """A class that encapsulates an automated Yahoo! fantasy manager."""
    def __init__(self, league_id=None, week = None, simulation_mode=False, as_of=None):
        if league_id is None:
            if default_league_id is None:
                raise ValueError('League id must be specified.  Default value was not present in .env')
            league_id = default_league_id
            
        self.simulation_mode = simulation_mode
        self.lg = FantasyLeague(league_id)
        self._stat_categories = None
        self.stat_categories_goalies = [stat['display_name'] for stat in self.lg.stat_categories() if stat['position_type'] == 'G']
        self._tm = None
        self._current_week = None
        self._game_weeks = {}
        self._as_of = as_of or datetime.now()
        self._game_weeks[self.current_week]= GameWeek(self, self.current_week, as_of = self._as_of)
        
        self.lg_cache = utils.LeagueCache(league_key=league_id)
        self.ppool = None
        self.nhl_scraper = Scraper()
        self.lineup = None
        self.opp_sum = None
        self.opp_team_name = None
        self.opp_team_key = None
        self.my_team: TeamInfo = None
        self.opponent: TeamInfo = None
        self._pred_bldr = None
        # self.init_prediction_builder()

    @property
    def tm(self):
        if not self._tm:
            self._tm = self.lg.to_team(self.lg.team_key())
        return self._tm

    @property
    def stat_categories(self):
        if not self._stat_categories:
            self._stat_categories = [stat['display_name'] for stat in self.lg.stat_categories() if stat['position_type'] == 'P']
        return self._stat_categories

    @property    
    def current_week(self):
        if not self._current_week:
            self._current_week = self.lg.current_week()
        return self._current_week

    def week_for_day(self, day):
        for _, game_week in self._game_weeks.items():
            if day in game_week.date_range:
                return game_week
        # not a loaded week.  can only get next week, yahoo only supports 1 week in advance
        next_game_week = GameWeek(self,self.current_week + 1, day)
        if day in next_game_week.date_range:
            self._game_weeks[self.current_week + 1] = next_game_week
            return next_game_week
        else:
            raise Exception("Can only support as of date in current week or the next week")
    
    def game_week(self, week_number=None)->GameWeek:
        week_number = week_number or self.current_week
        if week_number not in self._game_weeks.keys():
            try:
                start_date, _ = self.lg._date_range_of_played_or_current_week(week_number)
            except StopIteration:
                today = date.today()
                start_date = today + timedelta(days=-today.weekday(), weeks=1)
            game_week = GameWeek(self,week_number, start_date)
            self._game_weeks[week_number] = game_week
        return self._game_weeks[week_number]
        
    def add_to_blacklist(self, plyr_name):
        self.blacklist.append(plyr_name)
        self._save_blacklist()

    def remove_from_blacklist(self, plyr_name):
        if plyr_name not in self.blacklist:
            return False
        else:
            self.blacklist.remove(plyr_name)
            self._save_blacklist()
            return True

    def get_blacklist(self):
        return self.blacklist

    @property
    def pred_bldr(self):
        """Will load and return the prediction builder"""
        def loader():
            # module = self._get_prediction_module()
            # func = getattr('csh_fantasy_bot',
            #                self.cfg['Prediction']['builderClassLoader'])
            # return fantasysp_scrape.Parser(scoring_categories=self.stat_categories)
            #TODO should also retrieve all players on rosters in fantasy league, some could be outside default limit for predictor
            return yahoo_scraping.YahooPredictions(self.lg.league_id)
            
        try:
            expiry = timedelta(minutes=3 * 24 * 60)
            self._pred_bldr = self.lg_cache.load_prediction_builder(expiry, loader)
        except Exception as e:
            print("Error retrieving new projections, use existing if avail")
            self._pred_bldr = self.lg_cache.load_prediction_builder(None, None,ignore_expiry=True)
        return self._pred_bldr

    def fetch_cur_lineup(self):
        """Fetch the current lineup as set in Yahoo!"""
        all_mine = self._get_orig_roster()
        pct_owned = self.lg.percent_owned([e['player_id'] for e in all_mine])
        for p, pct_own in zip(all_mine, pct_owned):
            if p['selected_position'] == 'BN' or \
                    p['selected_position'] == 'IR':
                p['selected_position'] = np.nan
            assert(pct_own['player_id'] == p['player_id'])
            p['percent_owned'] = pct_own['percent_owned']
            p['fantasy_status'] = int(self.tm.team_key.split('.')[-1])
        return all_mine

    def _get_predicted_stats(self, my_roster):

        self._fix_yahoo_team_abbr(my_roster)
        self.nhl_scraper = Scraper()

        nhl_teams = self.nhl_scraper.teams()
        nhl_teams.set_index("id")
        nhl_teams.rename(columns={'name': 'team_name'}, inplace=True)

        my_roster = my_roster.merge(nhl_teams, left_on='editorial_team_abbr', right_on='abbrev')
        my_roster.rename(columns={'id': 'team_id'}, inplace=True)

        players = self.pred_bldr.predict(my_roster)
        # start_week,end_week = self.lg.week_date_range(self.lg.current_week())
        # let's double check for players on my roster who don't have current projections.  We will create our own by using this season's stats
        ids_no_stats = list(
            players.query('G != G & position_type == "P" & status != "IR"').index.values)
        the_stats = self.lg.player_stats(ids_no_stats, 'season')
        
        for player_w_stats in the_stats:
            for stat in self.stat_categories:
                if player_w_stats['GP'] > 0:
                    players.loc[player_w_stats['player_id'], [stat]] = player_w_stats[stat] / player_w_stats['GP']
        return players

    def _fix_yahoo_team_abbr(self, df):
        nhl_team_mappings = {'LA': 'LAK', 'Ott': 'OTT', 'Bos': 'BOS', 'SJ': 'SJS', 'Anh': 'ANA', 'Min': 'MIN',
                             'Nsh': 'NSH',
                             'Tor': 'TOR', 'StL': 'STL', 'Det': 'DET', 'Edm': 'EDM', 'Chi': 'CHI', 'TB': 'TBL',
                             'Fla': 'FLA',
                             'Dal': 'DAL', 'Van': 'VAN', 'NJ': 'NJD', 'Mon': 'MTL', 'Ari': 'ARI', 'Wpg': 'WPG',
                             'Pit': 'PIT',
                             'Was': 'WSH', 'Cls': 'CBJ', 'Col': 'COL', 'Car': 'CAR', 'Buf': 'BUF', 'Cgy': 'CGY',
                             'Phi': 'PHI'}
        df["editorial_team_abbr"].replace(nhl_team_mappings, inplace=True)

    def fetch_all_players(self):
        def all_loader():
            return self.lg.all_players()

        expiry = datetime.timedelta(minutes=6 * 60 * 20)
        return self.lg_cache.load_all_players(expiry,all_loader)

    def fetch_waivers(self):
        return self.lg.waivers()

    def fetch_free_agents(self):
        return self.lg.free_agents()

    def produce_all_player_predictions(self):
        all_projections = self.pred_bldr.predict(self.all_players)

        players_no_projections_on_team = all_projections[(all_projections.G != all_projections.G) \
                    & (all_projections.fantasy_status != 'FA') \
                    & (all_projections.position_type != 'G')    ].index

        # self.log.warn(f"no projections for players: {all_projections[all_projections.G != all_projections.G) & (all_projections.fantasy_status != 'FA')].index.values}")       
        # let's see if we rostered a player without projections.  if so we'll fall back on yahoo
                #retrieve_yahoo_rest_of_season_projections(self.league_id).loc[roster_results[roster_results.G != roster_results.G].index.values]
        if len(players_no_projections_on_team) > 0:
            yahoo_projections = retrieve_yahoo_rest_of_season_projections(self.lg.league_id)
            yahoo_projections[self.stat_categories] = yahoo_projections[self.stat_categories].div(yahoo_projections.GP, axis=0)
            for player_id in players_no_projections_on_team.values:
                try:
                    all_projections.update(yahoo_projections.loc[[player_id]]) 
                except KeyError:
                    print(f"Could not find projection for {all_projections.loc[player_id]}")
        all_projections = all_projections.round(2)
        produce_csh_ranking(all_projections, self.stat_categories, 
                    all_projections.index, ranking_column_name='fpts')

        #TODO this can be removed with support for goalies
        return all_projections[(all_projections.position_type == 'P') & ((all_projections.status != 'IR') & (all_projections.status != 'IR-LT'))]

    def fetch_league_lineups(self):
        scoring_results = {tm['team_key'].split('.')[-1]:self.lg.score_team_fpts(self.all_player_predictions[self.all_player_predictions.fantasy_status == int(tm['team_key'].split('.')[-1])], \
                                    date_range=self.week, simulation_mode=self.simulation_mode, team_id=tm['team_key'])[1] 
                                for tm in self.lg.teams()}
        return scoring_results

    def team_roster(self, team_id):
        all_projections = self.pred_bldr.predict(self.all_players.reset_index())
        projections_no_goalies = all_projections[all_projections.position_type == 'P']
        return projections_no_goalies[projections_no_goalies.fantasy_status == int(team_id.split('.')[-1])]

    def score_team(self,player_projections=None, opponent_scores=None, date_range=None, roster_change_set=None, simulation_mode=True, date_last_use_actuals=None, team_id=None):
        if date_range is None:
            date_range = self.game_week(self.current_week).date_range

        if player_projections is None:
            my_team_id = int(self.lg.team_key().split('.')[-1])
            game_week = self.week_for_day(date_range[0])
            player_projections = game_week.all_player_predictions[game_week.all_player_predictions.fantasy_status == my_team_id]
        
        if team_id is None:
            team_id = self.tm.team_key
        if opponent_scores is None:
            if self.opponent:
                opponent_scores = self.opponent.scores().sum()
            else:
                opponent_scores = defaultdict(lambda: 0)
        return self.lg.score_team(player_projections, date_range, opponent_scores, roster_change_set, simulation_mode=simulation_mode, team_id=team_id)


    def invalidate_free_agents(self, plyrs):
        if os.path.exists(self.lg_cache.free_agents_cache_file()):
            with open(self.lg_cache.free_agents_cache_file(), "rb") as f:
                free_agents = pickle.load(f)

            plyr_ids = [e["player_id"] for e in plyrs]
            LOG.info("Removing player IDs from free agent cache".
                             format(plyr_ids))
            new_players = [e for e in free_agents["payload"]
                           if e['player_id'] not in plyr_ids]
            free_agents['payload'] = new_players
            with open(self.lg_cache.free_agents_cache_file(), "wb") as f:
                pickle.dump(free_agents, f)

    def sum_opponent(self, opp_team_key):
        # Build up the predicted score of the opponent
        try:
            team_name = self._get_team_name(self.lg, opp_team_key)
            LOG.debug("opponent: {}".format(team_name))
        except LookupError:
            print("Not a valid team: {}:".format(opp_team_key))
            return(None, None)

        return (team_name, self.projected_league_scores[opp_team_key.split('.')[-1]])

    def optimize_with_pygenetic(self):
        """Utilize pygenetic to run GA."""
        

    def optimize_lineup_from_free_agents(self):
        """
        Optimize your lineup using all of your players plus free agents.
        """
        optimizer_func = self._get_lineup_optimizer_function()
        locked_plyrs = self.all_players[(self.all_players['fantasy_status'] == 2) & (self.all_players['percent_owned'] > 93) ].index.tolist()
        best_lineup = optimizer_func(self.score_comparer,
                                     self.ppool, locked_plyrs, self.lg, self.league_week, simulation_mode=True)

        if best_lineup:
            self.score_comparer.print_week_results(best_lineup.scoring_summary)


    def list_players(self, pos):
        self.display.printListPlayerHeading(pos)

        for plyr in self.ppool.iterrows():
            if pos in plyr[1]['eligible_positions']:
                self.display.printPlayer(pos, plyr)

    def find_in_lineup(self, name):
        for idx, p in enumerate(self.lineup):
            if p['name'] == name:
                return idx
        raise LookupError("Could not find player: " + name)

    def swap_player(self, plyr_name_del, plyr_name_add):
        if plyr_name_add:
            plyr_add_df = self.ppool[self.ppool['name'] == plyr_name_add]
            if(len(plyr_add_df.index) == 0):
                raise LookupError("Could not find player in pool: {}".format(
                    plyr_name_add))
            if(len(plyr_add_df.index) > 1):
                raise LookupError("Found more than one player!: {}".format(
                    plyr_name_add))
            plyr_add = plyr_add_df.iloc(0)[0]
        else:
            plyr_add = None

        idx = self.find_in_lineup(plyr_name_del)
        plyr_del = self.lineup[idx]
        assert(type(plyr_del.selected_position) == str)
        if plyr_add and plyr_del.selected_position not in \
                plyr_add['eligible_positions']:
            raise ValueError("Position {} is not a valid position for {}: {}".
                             format(plyr_del.selected_position,
                                    plyr_add['name'],
                                    plyr_add['eligible_positions']))

        if plyr_add:
            plyr_add['selected_position'] = plyr_del['selected_position']
        plyr_del['selected_position'] = np.nan
        if plyr_add:
            self.lineup[idx] = plyr_add
        else:
            del(self.lineup[idx])
        self.pick_bench()

    def apply_roster_moves(self, dry_run):
        """Make roster changes with Yahoo!

        :param dry_run: Just enumerate the roster moves but don't apply yet
        :type dry_run: bool
        """
        roster_chg = RosterChanger(self.lg, dry_run, self._get_orig_roster(),
                                   self.lineup, self.bench,
                                   self.injury_reserve)
        roster_chg.apply()

        # Change the free agent cache to remove the players we added
        if not dry_run and False:
            adds = roster_chg.get_adds_completed()
            self.invalidate_free_agents(adds)

    def pick_opponent(self, opp_team_key):
        (self.opp_team_name, self.opp_sum) = self.sum_opponent(opp_team_key)
        if self.opp_sum is not None:
            self.score_comparer.set_opponent(self.opp_sum.sum())

    def auto_pick_opponent(self):

        edit_wk = self.league_week
        LOG.debug("Picking opponent for week: {}".format(edit_wk))
        # (wk_start, wk_end) = self.lg.week_date_range(edit_wk)
        # edit_date = self.lg.edit_date()
        # if edit_date > wk_end:
        #     edit_wk += 1

        try:
            self.opp_team_key = self.tm.matchup(edit_wk)
        except RuntimeError:
            LOG.info("Could not find opponent.  Picking ourselves...")
            opp_team_key = self.lg.team_key()

        if self.opp_team_key is None:
            print('no opp found, plugging in Lee for playoffs')
            self.opp_team_key = '396.l.53432.t.4'
        self.pick_opponent(self.opp_team_key)

    def evaluate_trades(self, dry_run, verbose):
        """
        Find any proposed trades against my team and evaluate them.

        :param dry_run: True if we will evaluate the trades but not send the
            accept or reject through to Yahoo.
        :param verbose: If true, we will print details to the console
        :return: Number of trades evaluated
        """
        trades = self.tm.proposed_trades()
        LOG.info(trades)
        # We don't evaluate trades that we sent out.
        actionable_trades = [tr for tr in trades
                             if tr['tradee_team_key'] == self.tm.team_key]
        LOG.info(actionable_trades)

        if len(actionable_trades) > 0:
            for trade in actionable_trades:
                ev = self._evaluate_trade(trade)
                if verbose:
                    self._print_trade(trade, ev)
                LOG.warn("Accept={}    {}".format(ev, trade))
                if not dry_run:
                    if ev:
                        self.tm.accept_trade(trade['transaction_key'])
                    else:
                        self.tm.reject_trade(trade['transaction_key'])
        return len(actionable_trades)

    def _evaluate_trade(self, trade):
        """
        Evaluate a single trade

        :return: True if trade should be accepted.  False otherwise.
        """
        if False:
            return False
        else:
            assert(False), "No support for evaluating trades"

    def _print_trade(self, trade, ev):
        print("\nSending")
        for plyr in trade['trader_players']:
            print("  {}".format(plyr['name']))
        print("for your")
        for plyr in trade['tradee_players']:
            print("  {}".format(plyr['name']))
        print("\nTrade should be {}".format("accepted" if ev else "rejected"))

    def _get_team_name(self, lg, team_key):
        for team in lg.teams():
            if team['team_key'] == team_key:
                return team['name']
        raise LookupError("Could not find team for team key: {}".format(
            team_key))

    def _get_prediction_module(self):
        """Return the module to use for the prediction builder.

        The details about what prediction builder is taken from the config.
        """
        return importlib.import_module(
            self.cfg['Prediction']['builderModule'],
            package=self.cfg['Prediction']['builderPackage'])

    def _get_scorer_class(self):
        module = importlib.import_module(
            self.cfg['Scorer']['module'],
            package=self.cfg['Scorer']['package'])
        return getattr(module, self.cfg['Scorer']['class'])

    def _get_display_class(self):
        module = importlib.import_module(
            self.cfg['Display']['module'],
            package=self.cfg['Display']['package'])
        return getattr(module, self.cfg['Display']['class'])

    def _get_lineup_optimizer_function(self):
        """Return the function used to optimize a lineup.

        The config file is used to determine the appropriate function.
        """
        module = importlib.import_module('.roster_change_optimizer',
            package='csh_fantasy_bot')
        return getattr(module, 'optimize_with_genetic_algorithm')

    def _get_position_types(self):
        settings = self.lg.settings()
        position_types = {'mlb': ['B', 'P'], 'nhl': ['P']}
        return position_types[settings['game_code']]

    def _get_orig_roster(self):
        if self.simulation_mode:
            return self.tm.roster(day=self.week[0])
        else:
            return self.tm.roster(day=self.lg.edit_date())

    def compare_roster_yahoo_ideal(self, day=None):
        if not day:
            day = datetime.today()
        day = day.replace(hour=0, minute=0, second=0, microsecond=0)

        game_week = self.week_for_day(day)
        
        
        return game_week.compare_roster_yahoo_ideal(day)

    
    def _resolve_week(self, week):
        if isinstance(week, str):
            week = WS[week]
        if isinstance(week, WS):
            if week == WS.cur:
                week_n = self.current_week
            elif week == WS.next:
                week_n = self.current_week + 1
        else:    
            week_n = week or self.current_week
        return week_n

    def retreive_scores(self, week=None, ts=TS.me, **params) -> DataFrame:
        all_weeks = [i for i in range(1, self.current_week + 2)]
        # print(f'All weeks: {all_weeks}')
        # all_weeks = range(self.current_week + 2)
        # week_n = self._resolve_week(week)
        print(f'Week is: {all_weeks[week]} ({type(week)}), team selector: {ts}')
        results  = None
        for i in all_weeks[week]:
            print(f'Looking up for : {i}')
            i_scores = self.game_week(i).team_scores
            if results == None:
                results = i_scores 
        return results
        

        