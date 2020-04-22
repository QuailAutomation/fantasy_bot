"""Tests for RosterChangeSet."""

from datetime import datetime, timedelta
import pandas as pd
import pytest
import json

from csh_fantasy_bot.roster_change_optimizer import RosterChangeSet, RosterChangeSetEncoder, RosterException

@pytest.fixture
def a_change_date():
    """A convenient date to use for change_date."""
    return datetime(2020,4,4)

def est_json_encoding(a_change_date):
    """Ensure RosterChangeSet supports json encoding."""
    change_set = RosterChangeSet(max_allowed=2)
    change_set.add(3400, 3500, a_change_date)
    # out = json.dump(change_set.__dict__, lambda o: o.__dict__, indent=4)
    pass


def test_cant_add_player_twice(a_change_date):
    """Make sure a player cannot be added twice as roster add."""
    change_set = RosterChangeSet(max_allowed=2)
    change_set.add(player_out=34, player_in=44, change_date=a_change_date)
    try:
        change_set.add(player_out=35, player_in=44, change_date=a_change_date + timedelta(days=2))
        assert(False)
    except RosterException:
        pass
    

def test_can_drop_player_check(a_change_date):
    change_set = RosterChangeSet(max_allowed=1)
    change_set.add(player_out=34, player_in=44, change_date=a_change_date)
    assert(change_set.can_drop_player(34) == False )
    assert(change_set.can_drop_player(35) == True)


def test_get_by_date(a_change_date):
    change_set = RosterChangeSet()
    change_set.add(34,22,a_change_date)
    change_set.add(122,55,a_change_date)
    change_set.add(234,1,a_change_date + timedelta(days=1))

    assert (len(change_set) == 3)
    assert (len(change_set.get(a_change_date)) == 2)