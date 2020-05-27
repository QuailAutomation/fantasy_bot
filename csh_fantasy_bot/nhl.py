import datetime
import pandas as pd
import numpy as np
import logging

from collections import defaultdict

from nhl_scraper.nhl import Scraper
from nhl_scraper.rotowire import Scraper as RWScraper
from yahoo_fantasy_api import League, Team
from csh_fantasy_bot.roster import best_roster

import cProfile


    
# def _apply_roster_changes(self, roster_change_set ,single_date, all_projections):
#     roster_changes = roster_change_set.get(single_date)
#     if roster_changes is not None and len(roster_changes) > 0:
#         for row in roster_changes:
#             all_projections = all_projections.append(
#                 self.player_projections.loc[row['player_in'], :])
#             try:
#                 all_projections.drop(row['player_out'], inplace=True)
#             except KeyError as e:
#                 self.log.exception(e)
#     return all_projections

    

nhl_schedule = {}
nhl_scraper: Scraper = Scraper()

def find_teams_playing(game_day):
    """Get list of teams playing on game_day."""
    global nhl_schedule
    global nhl_scraper
    if game_day.strftime("%Y-%m-%d") not in nhl_schedule:
                nhl_schedule[
                    game_day.strftime("%Y-%m-%d")] = nhl_scraper.games_count(
                    game_day.to_pydatetime().date(), game_day.to_pydatetime().date())
    return nhl_schedule[game_day.strftime("%Y-%m-%d")]

# add elements of tuple - tuple(x+y for x, y in zip(a,b))



def score_team(player_projections, date_range, scoring_categories, roster_change_set=None, simulation_mode=True):
    """Score the team."""
    # let's only work in simulation mode for now
    assert(simulation_mode == True)
    # dict to keep track of how many games players play using projected stats
    games_played_projected = pd.Series([0] * len(player_projections), player_projections.index)
    for game_day in date_range:
        game_day_players = player_projections[player_projections.team_id.isin(find_teams_playing(game_day))]
        roster = best_roster(game_day_players.loc[:,['eligible_positions']].itertuples())
        for player in roster:
            games_played_projected[player.player_id] += 1

    return player_projections.loc[:,scoring_categories].multiply(games_played_projected, axis=0)
