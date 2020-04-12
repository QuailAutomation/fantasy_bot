"""Classes to represent League entities"""
from datetime import datetime, timedelta
import pandas as pd

from nhl_scraper.nhl import Scraper
from yahoo_fantasy_api import League
from csh_fantasy_bot import utils

class FantasyLeague(League):
    """Represents a league in yahoo."""
    
    def __init__(self, sc, league_id):
        """Instantiate the league."""
        super().__init__(sc, league_id)
        self.lg_cache = utils.LeagueCache()
    
    def all_players(self):
        """Return all players in league."""
        def all_loader():
            all = pd.DataFrame(League.all_players(self))
            self._fix_yahoo_team_abbr(all)
            self.nhl_scraper = Scraper()

            nhl_teams = self.nhl_scraper.teams()
            nhl_teams.set_index("id")
            nhl_teams.rename(columns={'name': 'team_name'}, inplace=True)

            all = all.merge(nhl_teams, left_on='editorial_team_abbr', right_on='abbrev')
            all.rename(columns={'id': 'team_id'}, inplace=True)
            return all

        expiry = timedelta(minutes=6 * 60 * 20)
        return self.lg_cache.load_all_players(expiry,all_loader)
    
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
    
    def draft_results(self):
        """Return json representation of draft."""
        return super().draft_results()