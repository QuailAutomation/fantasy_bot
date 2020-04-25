"""Classes to represent League entities."""
from datetime import datetime, timedelta
import pandas as pd
import logging

from nhl_scraper.nhl import Scraper
from yahoo_fantasy_api import League,Team
from csh_fantasy_bot import utils

from csh_fantasy_bot.yahoo_fantasy_tasks import oauth_token

class FantasyLeague(League):
    """Represents a league in yahoo."""

    def __init__(self, league_id):
        """Instantiate the league."""
        super().__init__(oauth_token, league_id)
        self.lg_cache = utils.LeagueCache()
        self.log = logging.getLogger(__name__)
        self.fantasy_status_code_translation = {'waivers':'W', 'freeagents': 'FA'}

    def all_players(self):
        """Return all players in league."""
        def all_loader():
            all_players= pd.DataFrame(super.all_players())
            self._fix_yahoo_team_abbr(all)
            self.nhl_scraper = Scraper()

            nhl_teams = self.nhl_scraper.teams()
            nhl_teams.set_index("id")
            nhl_teams.rename(columns={'name': 'team_name'}, inplace=True)

            all_players= all.merge(nhl_teams, left_on='editorial_team_abbr', right_on='abbrev')
            all_players.rename(columns={'id': 'team_id'}, inplace=True)
            return all_players

        expiry = timedelta(minutes=6 * 60 * 20)
        return self.lg_cache.load_all_players(expiry, all_loader)
    
    def transactions(self):
        """Return all players in league."""
        def transaction_loader():
            transactions= super.transactions()
            return transactions

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
            # start with all players, remove draftees, then apply roster changes up to this date
            all_players = self.all_players()
            all_players.set_index(['player_id'],inplace=True)
            draft_df = self.draft_results(format='Pandas')
            return all_players[~all_players.index.isin(draft_df.index)]
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
        all_players = self.all_players()

        all_players.set_index(keys=['player_id'], inplace=True)
        draft_df = self.draft_results(format='Pandas')
        all_players['fantasy_status'] = 'FA'
        all_players.loc[all_players.index.intersection(draft_df.index),'fantasy_status'] = draft_df['fantasy_team_id']
        post_draft_player_list = all_players.copy()
        # create a column fantasy_status.  will be team id, or FA (Free Agent), W-{Date} (Waivers)
        # TODO add waiver expiry column
        txns = self.transactions()
        asof_timestamp = datetime.timestamp(asof_date)
        for trans in zip(txns[::-2], txns[-2::-2]):
                if int(trans[1]['timestamp']) < asof_timestamp:
                    method = f"_apply_{trans[1]['type'].replace('/','')}"
                    if method in FantasyLeague.__dict__.keys():
                        FantasyLeague.__dict__[method](self, trans[0], post_draft_player_list)
                    elif method =='_apply_commish':
                        pass
                    else:
                        self.log.error("Unexpected transaction type: {method}")

        return post_draft_player_list

    def _apply_adddrop(self, trans_info, post_draft_player_list):
        print('Apply add/drop')
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
        # source_team_id = int(player_info['player'][1]['transaction_data']['source_team_key'].split('.')[-1])
        source_team_name = player_info['player'][1]['transaction_data']['source_team_name']
        destination = player_info['player'][1]['transaction_data']['destination_type']
        post_draft_player_list.at[player_id,'fantasy_status'] = self.fantasy_status_code_translation[destination]
        self.log.debug(f'dropping player: {player_name}, from: {source_team_name} to: {destination}')
