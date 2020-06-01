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
    # we are going to modify this as we iterate the dates.  so we need this for the math at end
    current_projections = player_projections.copy()
    # let's only work in simulation mode for now
    assert(simulation_mode == True)
    # dict to keep track of how many games players play using projected stats
    projected_games_played = pd.Series([0] * len(player_projections) , player_projections.index)
    # we need to look up roster changes by date so let's make a dict ourselves
    rc_dict = defaultdict(list)
    if roster_change_set:
        rc_in_ids = pd.Series([0] * len(roster_change_set.roster_changes), [rc.in_player_id for rc in roster_change_set.roster_changes] )
        projected_games_played = projected_games_played.append(rc_in_ids)
        for rc in roster_change_set.roster_changes:
            rc_dict[rc.change_date].append(rc)

    for game_day in date_range:
        for rc in rc_dict[game_day.date()]:
            current_projections = current_projections.append(rc.in_projections)
            current_projections.drop(rc.out_player_id, inplace=True)
            # remove out
        game_day_players = current_projections[current_projections.team_id.isin(find_teams_playing(game_day))]
        roster = best_roster(game_day_players.loc[:,['eligible_positions']].itertuples())
        for player in roster:
            projected_games_played[player.player_id] += 1

    return roster_change_set, player_projections.loc[:,scoring_categories].multiply(projected_games_played, axis=0)
