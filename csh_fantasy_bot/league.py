from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import logging
import time
import objectpath

from collections import defaultdict
from contextlib import suppress

from nhl_scraper.nhl import Scraper
from yahoo_fantasy_api import League,Team
from csh_fantasy_bot import utils
from csh_fantasy_bot import utils, fantasysp_scrape
from csh_fantasy_bot import scoring
from csh_fantasy_bot.yahoo_fantasy_tasks import oauth_token
from csh_fantasy_bot.nhl import find_teams_playing
from csh_fantasy_bot.roster import best_roster
from csh_fantasy_bot.scoring import ScoreComparer
from csh_fantasy_bot.score_gekko import score_gekko


from csh_fantasy_bot import RedisClient
# import pyarrow as pa
import pickle




def _roster_changes_as_day_dict(rcs):
    rc_dict = defaultdict(list)
    if rcs:
        for rc in rcs.roster_changes:
            rc_dict[rc.change_date].append(rc) 
    
    return rc_dict
    
class NoAsOfDateException(Exception):
    """Denote when trying to access state of league before setting asof."""

class FantasyLeague(League):
    """Represents a league in yahoo."""

    def __init__(self, league_id):
        """Instantiate the league."""
        super().__init__(oauth_token, league_id)
        self.lg_cache = utils.LeagueCache(league_id)
        self.log = logging.getLogger()
        self.fantasy_status_code_translation = {'waivers':'W', 'freeagents': 'FA'}
        # store datetime we are as-of use to roll transactions
        self.as_of_date = None
        self._all_players_df = None
        self.scorer = None
        self.score_comparer = None
        # TODO unsure if we should load this, or hardcode for performance
        # self.weights_series = pd.Series([1, .75, .5, .5, 1, .1, 1], index=["G", "A", "+/-", "PIM", "SOG", "FW", "HIT"])
        # the cached ACTUAL roster results
        self.cached_actual_results = {}

        self._roster_makeup = None

    def roster_makeup(self):
        if self._roster_makeup is None:
            positions = self.positions()
            roster_makeup = {}
            for position in positions.keys():
                roster_makeup[position] = int(positions[position]['count'])
            self._roster_makeup = roster_makeup
        return self._roster_makeup

    def scoring_categories(self, position_type=['P']):
        """Return list of categories that count for scoring."""
        return [stat['display_name'] for stat in League.stat_categories(self) if stat['position_type'] in position_type]

    def all_players(self):
        """Return dataframe of entire league for as of date."""
        if self.as_of_date:
            return self._all_players_df
        else:
            raise AsOfDateNotSetException()

    def _all_players(self):
        """Return all players in league."""
        def all_loader():
            all_players= pd.DataFrame(League.all_players(self))
            self._fix_yahoo_team_abbr(all_players)
            self.nhl_scraper = Scraper()

            nhl_teams = self.nhl_scraper.teams()
            nhl_teams.set_index("id")
            nhl_teams.rename(columns={'name': 'team_name'}, inplace=True)

            all_players['league_id'] = self.league_id

            all_players= all_players.merge(nhl_teams, left_on='editorial_team_abbr', right_on='abbrev')
            all_players.rename(columns={'id': 'team_id'}, inplace=True)
            return all_players

        expiry = timedelta(days=1)
        return self.lg_cache.load_all_players(expiry, all_loader)
    
    def transactions(self):
        """Return all players in league."""
        def transaction_loader():
            return League.transactions(self)

        expiry = timedelta(minutes=60)
        return self.lg_cache.load_transactions(expiry, transaction_loader)

    def team_by_id(self, team_id):
        """Use the last part of team id for resolve team."""
        return Team(self.sc, f"{self.league_id}.t.{team_id}")

    def team_by_key(self,team_key):
        """Resolve team for passed in key."""
        return Team(self.sc, team_key)

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
    
    def draft_results(self, format='List'):
        """Return the draft results."""
        raw = super().draft_results()

        if format != 'Pandas':
            return raw
        else:
            if len(raw) > 0:
                draft_df = pd.DataFrame(raw, columns=raw[0].keys())
                try:
                    draft_df['player_id'] = draft_df.player_key.str.split('.', expand=True)[2].astype('int16')
                    draft_df['fantasy_team_id'] = draft_df.team_key.str.split('.', expand=True)[4].astype('int8')
                    draft_df.set_index(['player_id'], inplace=True)
                except AttributeError:
                    print("Draft probably has not begun yet")
                return draft_df
            else:
                return pd.DataFrame()

    def team_by_id(self, team_id):
        """Return team assigned to fantasy team id.

        Args:
            team_id ([int]): The team index.
        """
        return self._all_players_df[self._all_players_df.fantasy_status == team_id]

    def free_agents(self, position=None):
        """Return the free agents at give datetime."""
        return self._all_players_df[self._all_players_df.fantasy_status == 'FA']

    def waivers(self, asof_date=None):
        """Return players on waivers."""
        return self._all_players_df[self._all_players_df.fantasy_status == 'W']

    def num_moves_made(self, week):
        if not week or week == self.current_week():
            number_moves_made = {}
            json = self.scoreboard()
            t = objectpath.Tree(json)
            my_team_id = super().team_key()
            elems = t.execute('$..matchup')
            for match in elems:
                number_moves_made[match['0']['teams']['0']['team'][0][0]['team_key']] = \
                    int(match['0']['teams']['0']['team'][0][11]['roster_adds']['value'])
                number_moves_made[match['0']['teams']['1']['team'][0][0]['team_key']] = \
                    int(match['0']['teams']['1']['team'][0][11]['roster_adds']['value'])
        
            return number_moves_made[my_team_id]
        else:
            return 0

    def as_of(self, asof_date):
        """Return the various buckets as of this date time."""
        if not self.as_of_date or asof_date != self.as_of_date:
            all_players = self._all_players()
            all_players = all_players.set_index(keys=['player_id'])
            draft_df = self.draft_results(format='Pandas')
            # create a column fantasy_status.  will be team id, or FA (Free Agent), W-{Date} (Waivers)
            # TODO add waiver expiry column
            all_players['fantasy_status'] = 'FA'
            all_players['waiver_date'] = np.nan
            #assign drafted players to their team
            if len(draft_df) > 0 and 'fantasy_team_id' in draft_df.columns:
                all_players.loc[all_players.index.intersection(draft_df.index),'fantasy_status'] = draft_df['fantasy_team_id']
            
            txns = self.transactions()
            asof_timestamp = datetime.timestamp(asof_date)
            for trans in zip(txns[::-2], txns[-2::-2]):
                    if int(trans[1]['timestamp']) < asof_timestamp:
                        method = f"_apply_{trans[1]['type'].replace('/','')}"
                        if method in FantasyLeague.__dict__.keys():
                            FantasyLeague.__dict__[method](self, trans, all_players)
                        elif method =='_apply_commish':
                            pass
                        else:
                            self.log.error("Unexpected transaction type: {method}")

            self.as_of_date = asof_date
            self._all_players_df = all_players
            self.scorer = None
            self.score_comparer = None
        return self

    def _apply_adddrop(self, txn_info, post_draft_player_list):
        trans_info = txn_info[0]
        txn_timestamp = datetime.fromtimestamp( int(txn_info[1]['timestamp']))
        self._add_player(trans_info['players']['0'], post_draft_player_list)
        self._drop_player(trans_info['players']['1'], post_draft_player_list, txn_timestamp)

    def _apply_add(self, txn_info, post_draft_player_list):
        trans_info = txn_info[0]
        self._add_player(trans_info['players']['0'], post_draft_player_list)

    def _apply_drop(self, txn_info, post_draft_player_list):
        trans_info = txn_info[0]
        txn_timestamp = datetime.fromtimestamp( int(txn_info[1]['timestamp']))
        self._drop_player(trans_info['players']['0'], post_draft_player_list, txn_timestamp)

    def _add_player(self, player_info, post_draft_player_list):
        player_id = int(player_info['player'][0][1]['player_id'])
        player_name = player_info['player'][0][2]['name']['full']
        dest_team_id = int(player_info['player'][1]['transaction_data'][0]['destination_team_key'].split('.')[-1])
        dest_team_name = player_info['player'][1]['transaction_data'][0]['destination_team_name']
        post_draft_player_list.at[player_id,'fantasy_status'] = dest_team_id
        self.log.debug(f'apply add, player: {player_name} to: {dest_team_name}')

    def _drop_player(self, player_info, post_draft_player_list, drop_date):
        player_id = int(player_info['player'][0][1]['player_id'])
        player_name = player_info['player'][0][2]['name']['full']
        source_team_name = player_info['player'][1]['transaction_data']['source_team_name']
        destination = player_info['player'][1]['transaction_data']['destination_type']
        waiver_days = int(self.settings()['waiver_time'])
        time_clear_waivers = datetime.combine((drop_date + timedelta(days=waiver_days + 1)), datetime.min.time())
        if time_clear_waivers > datetime.now():
            post_draft_player_list.at[player_id,'fantasy_status'] = self.fantasy_status_code_translation[destination]
            post_draft_player_list.at[player_id,'waiver_date'] = time_clear_waivers
        else:
            post_draft_player_list.at[player_id,'fantasy_status'] ='FA'
        self.log.debug(f'dropping player: {player_name}, from: {source_team_name} to: {destination}')

    def stat_predictor(self):
        """Load and return the prediction builder."""
        def loader():
            return fantasysp_scrape.Parser(scoring_categories=self.scoring_categories())

        expiry = timedelta(days=7)
        return self.lg_cache.load_prediction_builder(expiry, loader)


    def get_projections(self):
        """Return projections dataframe."""
        if not self.as_of_date:
            raise NoAsOfDateException("As of date not specified yet")
        
        return self.stat_predictor().predict(self._all_players_df)

    def _actuals_for_team_day(self, team_id, game_day, scoring_categories):
        _game_day = game_day.to_pydatetime().date()
        actual_cache_key = f"actuals:{team_id}-{_game_day}"
        results = RedisClient().conn.get(actual_cache_key)
        if not results:
            the_roster = self.team_by_key(team_id).roster(day=game_day)
            opp_daily_roster = pd.DataFrame(the_roster)
            lineup = opp_daily_roster.query('selected_position != "BN" & selected_position != "G"')
            stats = self.player_stats(lineup.player_id.tolist(), "date", date=_game_day)
            daily_stats = pd.DataFrame(stats).loc[:,['player_id'] + scoring_categories]
            daily_stats.loc[:,'score_type'] = 'a'
            daily_stats.replace('-', np.nan, inplace=True)
            daily_stats.set_index('player_id',inplace=True)
            time.sleep(.5)
            results = daily_stats.loc[~daily_stats.G.isnull(),:]
            
            # df_compressed = pa.serialize(daily_stats).to_buffer().to_pybytes()
            RedisClient().conn.set(actual_cache_key, pickle.dumps(daily_stats))
        else:
            results = pickle.loads(results)
            # results = pa.deserialize(results)
        return results

    def score_team(self, player_projections, date_range, roster_change_set=None, simulation_mode=True, date_last_use_actuals=None, team_id=None):
        """Score the team.

        Args:
            player_projections (DataFrame): Projections for all players on the team
            date_range (pd.DateRange): Date range to project for
            scoring_categories (list): List of player scoring categories scored
            roster_change_set (RosterChangeSet, optional): Changes to make throughout the scoring period. Defaults to None.
            simulation_mode (bool, optional): Ignores actuals if games already played, still uses projected scoring. Defaults to True.
            date_last_use_actuals (DateTime): If not in simulation mode, this value sets the last day to use actual scoring instead of projecting. 
            team_id (string, optional): Need this to look up actual scores for days which have passed.

        Returns:
            [type]: [description]
        """
        # we are going to modify this as we iterate the dates.  so we need this for the math at end
        current_projections = player_projections.copy()
        # projections for players who may play.  changes with roster changes during period
        projections_with_added_players = player_projections.copy()
        current_projections.sort_values(by='fpts', ascending=False, inplace=True)
        # dict to keep track of how many games players play using projected stats
        projected_games_played = defaultdict(int)
        # we need to look up roster changes by date so let's make a dict ourselves
        rc_dict = defaultdict(list)
        if roster_change_set:
            rc_dict = _roster_changes_as_day_dict(roster_change_set)

        scoring_categories = self.scoring_categories()

        roster_week_results = None
        if not (simulation_mode or date_last_use_actuals):
            # if date_last_use_actuals is not set, we default it to 1 second before midnight today
            date_last_use_actuals = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)  # can't support today yet, need to watch for completed games, etc.

        for game_day in date_range:
            roster_results = None
        
            for rc in rc_dict[game_day.date()]:
                # TODO should really figure out how to deal with this.  sometimes it is string, sometimes list. 
                # i think has to do with serializing via jsonpickle
                with suppress(Exception):
                    rc.in_projections['eligible_positions'] = pd.eval(rc.in_projections['eligible_positions'])
                # add player in projections to projection dataframe
                current_projections = current_projections.append(rc.in_projections)
                projections_with_added_players = projections_with_added_players.append(rc.in_projections)
                current_projections.drop(rc.out_player_id, inplace=True)
                current_projections.sort_values(by='fpts', ascending=False, inplace=True)
            
            # let's see if we should grab actuals
            if not simulation_mode and game_day < date_last_use_actuals:
                roster_results= self._actuals_for_team_day(team_id, game_day, scoring_categories)
            else:
                game_day_players = projections_with_added_players[projections_with_added_players.team_id.isin(find_teams_playing(game_day.to_pydatetime().date()))]
                if len(game_day_players) > 0:
                    roster = best_roster(game_day_players.loc[:,['eligible_positions']].itertuples())
                    rostered_players = [player.player_id for player in roster]
                    roster_results = projections_with_added_players.loc[rostered_players, scoring_categories]
                    roster_results.loc[:,'score_type'] = 'p'

                    if len(roster_results[roster_results.G != roster_results.G].index.values) > 0:
                        self.log.warn(f"no projections for players: {roster_results[roster_results.G != roster_results.G].index.values}")

            if roster_results is not None and len(roster_results) > 0:
                roster_results['play_date'] = game_day
                if roster_week_results is None:
                    roster_week_results = roster_results
                else:
                    roster_week_results = roster_week_results.append(roster_results)


        #TODO maybe we should formalize a return structure
        if len(roster_week_results) > 0:
            roster_week_results.reset_index(inplace=True)
            roster_week_results.set_index(['play_date', 'player_id'], inplace=True)
        return roster_change_set, roster_week_results
    
    def score_team_new(self, player_projections, date_range, opponent_scores, roster_change_set=None, simulation_mode=True, date_last_use_actuals=None, team_id=None):
        date_last_use_actuals = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)
        if date_last_use_actuals < date_range[0]:
            date_last_use_actuals = date_range[0]
        scoring_categories = self.scoring_categories()
        # lets add actuals, they can't be optimized
        actuals_results = self.score_actuals(team_id,date_range[date_range.slice_indexer(date_range[0],date_last_use_actuals)], scoring_categories)
        actual_results_summed = None
        if actuals_results is not None:
            actual_results_summed = actuals_results.sum()

        roster_makeup = self.roster_makeup()    
        projected_results = score_gekko(player_projections, team_id, opponent_scores,scoring_categories,date_range[date_range.slice_indexer(date_last_use_actuals)], roster_makeup, roster_change_set=roster_change_set, actual_scores=actual_results_summed)

        if actuals_results is not None:
            actuals_results.reset_index(inplace=True)
            roster_week_results = actuals_results.append(projected_results)
        else:
            roster_week_results = projected_results
        roster_week_results.set_index(['play_date', 'player_id'], inplace=True)
        return roster_change_set, roster_week_results

    def score_actuals(self, team_id, date_range, scoring_categories):
        # TODO cache the group of actuals
        # grab actuals
        roster_week_results = None
        for game_day in date_range:
            roster_results= self._actuals_for_team_day(team_id, game_day, scoring_categories)
            # get rid of players that didnt play
            roster_results = roster_results[roster_results.G == roster_results.G]
            if roster_results is not None and len(roster_results) > 0:
                roster_results['play_date'] = game_day
                if roster_week_results is None:
                    roster_week_results = roster_results
                else:
                    roster_week_results = roster_week_results.append(roster_results)
        return roster_week_results
