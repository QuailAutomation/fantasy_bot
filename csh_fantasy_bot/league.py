"""Classes to represent League entities."""
from datetime import datetime, timedelta
import pandas as pd
import logging

from nhl_scraper.nhl import Scraper
from yahoo_fantasy_api import League,Team
from csh_fantasy_bot import utils
from csh_fantasy_bot import utils, fantasysp_scrape
from csh_fantasy_bot.yahoo_fantasy_tasks import oauth_token
from csh_fantasy_bot.nhl import BestRankedPlayerScorer
from csh_fantasy_bot.scoring import ScoreComparer


class FantasyLeague(League):
    """Represents a league in yahoo."""

    def __init__(self, league_id):
        """Instantiate the league."""
        super().__init__(oauth_token, league_id)
        self.lg_cache = utils.LeagueCache(league_id)
        self.log = logging.getLogger(__name__)
        self.fantasy_status_code_translation = {'waivers':'W', 'freeagents': 'FA'}
        # store datetime we are as-of use to roll transactions
        self.as_of_date = None
        self._all_players_df = None
        self.scorer = None
        self.score_comparer = None

    def scoring_categories(self, position_type=['P']):
        """Return list of categories that count for scoring."""
        return [stat['display_name'] for stat in League.stat_categories(self) if stat['position_type'] in position_type]

    def all_players(self):
        """Return dataframe of entire league for as of date."""
        if self.as_of_date:
            return self._all_players_df
        else:
            raise  AsOfDateNotSetException

    def _all_players(self):
        """Return all players in league."""
        def all_loader():
            all_players= pd.DataFrame(League.all_players(self))
            self._fix_yahoo_team_abbr(all_players)
            self.nhl_scraper = Scraper()

            nhl_teams = self.nhl_scraper.teams()
            nhl_teams.set_index("id")
            nhl_teams.rename(columns={'name': 'team_name'}, inplace=True)

            all_players= all_players.merge(nhl_teams, left_on='editorial_team_abbr', right_on='abbrev')
            all_players.rename(columns={'id': 'team_id'}, inplace=True)
            return all_players

        expiry = timedelta(days=30)
        return self.lg_cache.load_all_players(expiry, all_loader)
    
    def transactions(self):
        """Return all players in league."""
        def transaction_loader():
            return League.transactions(self)

        expiry = timedelta(minutes=6 * 60 * 20)
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
            draft_df = pd.DataFrame(raw, columns=raw[0].keys())
            draft_df['player_id'] = draft_df.player_key.str.split('.', expand=True)[2].astype('int16')
            draft_df['fantasy_team_id'] = draft_df.team_key.str.split('.', expand=True)[4].astype('int8')
            draft_df.set_index(['player_id'], inplace=True)
            return draft_df

    def free_agents(self, position=None, asof_date=None):
        """Return the free agents at give datetime."""
        if asof_date:
            players_df = self.as_of(asof_date)
            return players_df[players_df.fantasy_status == 'FA']
        else:
            return super().free_agents(position)

    def waivers(self, asof_date=None):
        """Return players on waivers on date."""
        if asof_date:
            # start with all players, remove draftees, then apply roster changes up to this date
            pass
        else:
            return super().waivers()

    def as_of(self, asof_date):
        """Return the various buckets as of this date time."""
        if not self.as_of_date or asof_date != self.as_of_date:
            all_players = self._all_players()
            all_players = all_players.set_index(keys=['player_id'])
            draft_df = self.draft_results(format='Pandas')
            # create a column fantasy_status.  will be team id, or FA (Free Agent), W-{Date} (Waivers)
            # TODO add waiver expiry column
            all_players['fantasy_status'] = 'FA'
            #assign drafted players to their team
            all_players.loc[all_players.index.intersection(draft_df.index),'fantasy_status'] = draft_df['fantasy_team_id']
            
            txns = self.transactions()
            asof_timestamp = datetime.timestamp(asof_date)
            for trans in zip(txns[::-2], txns[-2::-2]):
                    if int(trans[1]['timestamp']) < asof_timestamp:
                        method = f"_apply_{trans[1]['type'].replace('/','')}"
                        if method in FantasyLeague.__dict__.keys():
                            FantasyLeague.__dict__[method](self, trans[0], all_players)
                        elif method =='_apply_commish':
                            pass
                        else:
                            self.log.error("Unexpected transaction type: {method}")

            self.as_of_date = asof_date
            self._all_players_df = all_players
            self.scorer = None
            self.score_comparer = None
        return self

    def _apply_adddrop(self, trans_info, post_draft_player_list):
        self._add_player(trans_info['players']['0'], post_draft_player_list)
        self._drop_player(trans_info['players']['1'], post_draft_player_list)

    def _apply_add(self, trans_info, post_draft_player_list):
        self._add_player(trans_info['players']['0'], post_draft_player_list)

    def _apply_drop(self, trans_info, post_draft_player_list):
        self._drop_player(trans_info['players']['0'], post_draft_player_list)

    def _add_player(self, player_info, post_draft_player_list):
        player_id = int(player_info['player'][0][1]['player_id'])
        player_name = player_info['player'][0][2]['name']['full']
        dest_team_id = int(player_info['player'][1]['transaction_data'][0]['destination_team_key'].split('.')[-1])
        dest_team_name = player_info['player'][1]['transaction_data'][0]['destination_team_name']
        post_draft_player_list.at[player_id,'fantasy_status'] = dest_team_id
        self.log.debug(f'apply add, player: {player_name} to: {dest_team_name}')

    def _drop_player(self, player_info, post_draft_player_list):
        player_id = int(player_info['player'][0][1]['player_id'])
        player_name = player_info['player'][0][2]['name']['full']
        source_team_name = player_info['player'][1]['transaction_data']['source_team_name']
        destination = player_info['player'][1]['transaction_data']['destination_type']
        post_draft_player_list.at[player_id,'fantasy_status'] = self.fantasy_status_code_translation[destination]
        self.log.debug(f'dropping player: {player_name}, from: {source_team_name} to: {destination}')

    def stat_predictor(self):
        """Load and return the prediction builder."""
        def loader():
            return fantasysp_scrape.Parser()

        expiry = timedelta(days=7)
        return self.lg_cache.load_prediction_builder(expiry, loader)

    # def score(self, date_range, team_key, opponent, roster_change_sets=None):
    #     all_players = self.stat_predictor().predict(self.as_of(date_range[0]))
    #     if not self.scorer:
    #         league_scores = {tm['team_key']:BestRankedPlayerScorer(self, self.team_by_key(tm['team_key']), \
    #                         all_players).score(date_range, simulation_mode=True) for tm in self.teams()}
    #         scoring_list = [league_scores[x] for x in league_scores.keys()]
    #         self.score_comparer = ScoreComparer(scoring_list,all_players,self.scoring_categories())
    #         self.score_comparer.set_opponent(league_scores[f'{self.league_id}.t.{opponent}'].sum())

    #         self.scorer = BestRankedPlayerScorer(self, self.team_by_key(team_key), all_players)

    #     if roster_change_sets:
    #         for change_set in roster_change_sets:
    #             the_score = self.scorer.score(date_range, change_set)
    #             change_set.scoring_summary = the_score.reset_index()
    #             change_set.score = self.score_comparer.compute_score(the_score)
    #         return roster_change_sets
    #     else:
    #         the_score = self.scorer.score(date_range)
    #         return the_score.reset_index()

    def get_projections(self):
        """Return projections dataframe."""
        if not self.as_of_date:
            raise RuntimeError("As of date not specified yet")
        
        return self.stat_predictor().predict(self._all_players_df)


class AsOfDateNotSetException(Exception):
    """Denotes when trying to access state of league before setting asof."""