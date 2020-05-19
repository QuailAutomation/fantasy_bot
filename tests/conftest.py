"""Pytest conf items."""
import pytest
import pickle
import json
import datetime
import pandas as pd 

from csh_fantasy_bot.league import FantasyLeague

@pytest.fixture
def season_start_date():
    """Hardcode season start date."""
    return datetime.datetime(2019,10,2)

@pytest.fixture
def all_players_df():
    """Return all players dataframe."""
    with open('tests/all_players.pkl', "rb") as f:
        return pickle.load(f)['payload']

@pytest.fixture
def league(mocker, all_players_df):
    """League object."""
    league =  FantasyLeague('396.l.53432')
    # mock the yahoo web endpoint by using files
    yhandler_mock = mocker.MagicMock()
    # with open('tests/transactions.json') as json_file:
    #     yhandler_mock.transactions.return_value = json.load(json_file)
    with open('tests/draft.json') as json_file:
        yhandler_mock.get_draft_results.return_value = json.load(json_file)
    with open('tests/league_settings.json') as json_file:
        yhandler_mock.get_settings_raw.return_value = json.load(json_file)  
    
    league.all_players = mocker.MagicMock(return_value=all_players_df)
    league.scoring_categories = mocker.MagicMock(return_value=all_players_df)    
    
    with open('tests/pred_builder.pkl', "rb") as f:
        league.stat_predictor = mocker.MagicMock(return_value=pickle.load(f)['payload'])    
    with open('tests/transactions.pkl', "rb") as f:
        league.transactions = mocker.MagicMock(return_value=pickle.load(f)['payload'])    
    # with open('tests/transactions.json', "rb") as f:
    #     league.transactions = mocker.MagicMock(return_value=League.transactions())    
    
    league.yhandler = yhandler_mock

    return league

@pytest.fixture
def league_post_draft(league, season_start_date):
    """Return league post-draft."""
    return league.as_of(season_start_date)

@pytest.fixture
def default_player_scoring_stats(league):
    """Fantasy default player scoring stats."""
    return ["G", "A", "+/-", "PIM", "SOG", "FW", "HIT"]

@pytest.fixture
def scoring_weights(default_player_scoring_stats):
    """Weighting for each stat used for determining overall quality of player."""
    return pd.Series([1, .75, 1, .5, 1, .1, 1], index=default_player_scoring_stats)