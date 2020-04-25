"""
Tests for FantasyLeague.

Going to use saved datafiles for Yahoo endpoint, so can hardcode 
checks to make sure results don't change.
"""
import pytest
import json
import datetime
import pickle

from csh_fantasy_bot.league import FantasyLeague

@pytest.fixture
def season_start():
    """Hardcode season start date."""
    return datetime.datetime(2019,10,2)

@pytest.fixture
def league(mocker):
    """League object."""
    league =  FantasyLeague('396.l.53432')
    # mock the yahoo web endpoint by using files
    yhandler_mock = mocker.MagicMock()
    with open('tests/transactions.json') as json_file:
        yhandler_mock.get_transactions.return_value = json.load(json_file)
    with open('tests/draft.json') as json_file:
        yhandler_mock.get_draft_results.return_value = json.load(json_file)
    with open('tests/league_settings.json') as json_file:
        yhandler_mock.get_settings_raw.return_value = json.load(json_file)  
    with open('tests/all_players.pkl', "rb") as f:
        league.all_players = mocker.MagicMock(return_value=pickle.load(f)['payload'])    
    
    league.yhandler = yhandler_mock

    return league

def test_load_transactions(league):
    """Load the transactions."""
    txns = league.transactions()
    assert(len(txns) == 768)

def test_load_draft(league):
    """Load the draft results."""
    draft = league.draft_results()
    assert(len(draft) == 144)
    #mcdavid 1st
    assert(draft[0]['player_key']  == '396.p.6743')
    # carter hart 67th
    assert(draft[66]['player_key']  == '396.p.7156')
    # zadorov last
    assert(draft[-1]['player_key']  == '396.p.5995')

def test_get_free_agents_season_start(league, season_start):
    """Return dataframe of all free agents."""
    # equals all players minus drafted players
    # make sure none of the draft players in list
    free_agents = league.free_agents(asof_date=season_start)
    drafted = league.draft_results(format='Pandas')
    assert(len(free_agents.index.intersection(drafted.index)) == 0), "Should be no drafted players as free agents"
    # could make sure all 'all_players' that weren't drafted are here

def test_fantasy_status_nov_1(league):
    """Return dataframe of all free agents."""
    nov_1 = datetime.datetime(2019,11,1)
    players = league.as_of(nov_1)
    # make sure sammy blais is not a free agent, he was picked up oct 31
    assert(players.loc[6544, 'fantasy_status'] != 'FA')

def test_get_waivers_asof_date(league):
    """Return player on waivers for given time."""
    pass

def get_team_roster(league, date):
    """Return team roster at given date."""
    pass
