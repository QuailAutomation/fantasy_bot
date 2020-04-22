"""Tests for RosterChangeSet."""
import datetime
import pandas as pd
import pytest
import json

from csh_fantasy_bot.roster_change_optimizer import RosterChangeSet, RosterChangeSetEncoder

@pytest.fixture
def change_date():
    return datetime.date(2020, 4, 4)

def test_json_encoding(change_date):
    """Ensure RosterChangeSet supports json encoding."""
    change_set = RosterChangeSet(max_allowed=2)
    change_set.add(3400, 3500, change_date)
    out = json.dump(change_set.__dict__, lambda o: o.__dict__, indent=4)
    pass

