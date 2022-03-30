import os
import datetime
from dotenv import load_dotenv

from csh_fantasy_bot.yahoo_scraping import PredictionType
from csh_fantasy_bot.utils import CacheBase, LeagueCache
from csh_fantasy_bot.bot import ManagerBot
from csh_fantasy_bot.yahoo_projections import produce_csh_ranking
from .selector import PlayerSelector
load_dotenv()
default_league_id = os.getenv('default_league_id',default=None)
default_cache_dir = os.getenv('cache_dir',default=None)

def _league_id_or_default(league_id):
    if league_id is not None: 
        return league_id
    else:
     return default_league_id

class PredictionsCache(CacheBase):
    def __init__(self, cache_dir=None):
        if cache_dir is None:
            cache_dir = default_cache_dir
        super().__init__(cache_dir)

    def predictions_cache_file(self, league_id, prediction_type, as_of):
        return f"{self.cache_dir}/{league_id}/predictions/{as_of}-{prediction_type}.pkl"

    def load_lineup(self, expiry, loader):
        return self.run_loader(self.lineup_cache_file(), expiry, loader)

    def load_predictions(self, prediction_type, league_id=None, as_of=None):
        league_id = _league_id_or_default(league_id)
        if as_of is not None:
            raise ValueError("As of date not yet supported")
        as_of = datetime.now().strftime("%Y-%m-%d")
        return self.run_loader(self.predictions_cache_file(league_id, prediction_type,as_of),None,None)
    
class FantasyData:
    def __init__(self, league_id=None, week=None) -> None:
        self.league_id = _league_id_or_default(league_id)
        if week is not None:
            raise ValueError("Setting week not supported yet")
        self.__manager_bot = None
        self.__selectors = None
        self._week = None
    @property
    def _manager_bot(self):
        if self.__manager_bot is None:
            self.__manager_bot =  ManagerBot(self.league_id)
        return self.__manager_bot
    
    @property 
    def week(self):
        if self._week is None:
            self._week = self._manager_bot.current_week
        return self._week

    @property
    def all_players(self):
        return self._manager_bot.lg._all_players().set_index("player_id")

    def player_projections(self, game_week=None, as_of=None, prediction_type = PredictionType.rest_season):
        if game_week is not None:
            raise ValueError('Current game week only supported')
        if as_of is not None:
            raise ValueError('as of not supported')
        if prediction_type != PredictionType.rest_season:
            raise ValueError('only end season predictions supported.')    
        # player_projections = self.__manager_bot.pred_bldr.predict(self.all_players)
        # return produce_csh_ranking(player_projections,self.scoring_categories, ranking_column_name='fpts')
        return self._manager_bot.game_week().all_player_predictions
    @property
    def draft_results(self, format='Pandas'):
        return self._manager_bot.lg.draft_results(format)
    @property
    def scoring_categories(self):
        return self._manager_bot.stat_categories

    @property
    def selectors(self)->PlayerSelector:
        if self.__selectors is None:
            my_id = int(self._manager_bot.tm.team_key.split('.')[-1])
            my_opp = int(self._opponent_id.split('.')[-1])
            self.__selectors = PlayerSelector(self.player_projections(),my_id, my_opp)
        return self.__selectors

    @property
    def current_week(self):
        return self._manager_bot.lg.current_week()
    
    @property
    def _opponent_id(self):
        return self._manager_bot.tm.matchup(self.current_week)