"""Tests."""
import pandas as pd
import numpy as np
import pytest

# nice for when printing dataframes to console
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

# player_stats = ["G", "A", "+/-", "PIM", "SOG", "FW", "HIT"]
# weight importance of the player stats
# weights_series = pd.Series([2, 1.75, .5, .5, .5, .3, .5], index=player_stats)

# roster_makeup = pd.Index("C,C,LW,LW,RW,RW,D,D,D,D".split(","))
# roster_position_counts = roster_makeup.value_counts()


@pytest.fixture
def builder():
    """Instance of the builder."""
    from csh_fantasy_bot.roster import RecursiveRosterBuilder

    return RecursiveRosterBuilder(roster_makeup=pd.Index("C,C,LW,LW,RW,RW,D,D,D,D".split(",")),
                                stats_weights=pd.Series([2, 1.75, .5, .5, .5, .3, .5], index=["G", "A", "+/-", "PIM", "SOG", "FW", "HIT"]))

@pytest.fixture
def team():
    """Sample setup of a team."""
    my_team = pd.read_csv('./tests/my-team.csv',
                      converters={"eligible_positions": lambda x: x.strip("[]").replace("'", "").split(", ")})
    my_team.set_index('player_id', inplace=True)
    return my_team

# fpts is a weighted score assigned to each player which reflects their overall skill
# for fantasy, and is used to choose players relative to others


# def find_dups_ignore_nan(x):
#     print(x.dropna())


def test_another(builder, team):
    player_ids = [4471, 7498, 5698]
    day1_roster = team.loc[player_ids, :]

    # builder = roster.DailyRosterBuilder()
    best_roster = builder.find_best(day1_roster)
    assert(player_ids in best_roster.values)
    # assert 7498 in best_roster.values
    # assert best_roster['C1'] == 5462

    # best_roster = builder.find_best(day1_roster)
    # day_results = my_team.loc[best_roster.drop('pts').values.astype(int).tolist(), player_stats]


# def test_handle_nan_in_rosters():
#     df = pd.read_csv('find-nans.csv')
#     df.apply(find_dups_ignore_nan, axis=1)
#     pass
# simple test which has 2 centres(C), and one player that be slotted into C,RW.
# the C,RW player has a higher fantasy (fpts) ranking than 1 of the centres so
# first iteration would probably place him in C, thus blocking out the 3rd player
# who can only play cent
# re.
def test_daily_results1(builder, team):
    # this test will work on a subset of 3 players
    day1 = [5462, 5984, 3982]
    day1_roster = team.loc[day1, :]
    best_roster = builder.find_best(day1_roster)
    print(best_roster.head(20))
    assert(best_roster['RW.1'] == 5984)
    assert(best_roster['C.1'] == 5462)
    assert(best_roster['C.2'] == 3982)


def test_daily_results2(builder, team):
    # this test has 5 dmen, which is more than allowed by roster
    player_ids = [5462, 5984, 3982, 4683, 4471, 5363, 5698, 4351, 4491, 4472, 8614, 6614, 7498]
    day1_roster = team.loc[player_ids, :]

    best_roster = builder.find_best(day1_roster)
    assert(best_roster['RW.1'] == 5984)
    assert(best_roster['C.1'] == 5462)
    assert(best_roster['C.2'] == 3982)


def test_single_lw_rw(builder, team):
    player_ids = [5698]
    day1_roster = team.loc[player_ids, :]

    best_roster = builder.find_best(day1_roster)
    assert(best_roster['LW.1'] == 5698)
