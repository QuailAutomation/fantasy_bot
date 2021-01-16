import datetime
import pandas as pd
import numpy as np
import logging

from collections import defaultdict
from contextlib import suppress


from nhl_scraper.nhl import Scraper
from nhl_scraper.rotowire import Scraper as RWScraper
from yahoo_fantasy_api import League, Team
from csh_fantasy_bot.roster import best_roster

import cProfile


nhl_schedule = {}
nhl_scraper: Scraper = Scraper()

log = logging.getLogger(__name__)
DATE_FORMAT = "%Y-%m-%d"
def find_teams_playing(game_day):
    """Get list of teams playing on game_day."""
    global nhl_schedule
    global nhl_scraper
    if game_day.strftime(DATE_FORMAT) not in nhl_schedule:
                nhl_schedule[
                    game_day.strftime(DATE_FORMAT)] = nhl_scraper.games_count(
                    game_day.to_pydatetime().date(), game_day.to_pydatetime().date())
    return nhl_schedule[game_day.strftime(DATE_FORMAT)]

# add elements of tuple - tuple(x+y for x, y in zip(a,b))



def score_team(player_projections, date_range, scoring_categories, roster_change_set=None, simulation_mode=True):
    """Score the team."""
    # we are going to modify this as we iterate the dates.  so we need this for the math at end
    current_projections = player_projections.copy()
    projections_with_added_players = player_projections.copy()
    current_projections.sort_values(by='fpts', ascending=False, inplace=True)
    # let's only work in simulation mode for now
    assert(simulation_mode == True)
    # dict to keep track of how many games players play using projected stats
    projected_games_played = defaultdict(int)
    # we need to look up roster changes by date so let's make a dict ourselves
    rc_dict = defaultdict(list)
    if roster_change_set:
        for rc in roster_change_set.roster_changes:
            rc_dict[rc.change_date].append(rc)

    for game_day in date_range:
        
        needs_sort = False
        for rc in rc_dict[game_day.date()]:
            # TODO should really figure out how to deal with this.  sometimes it is string, sometimes list. 
            # i think has to do with serializing via jsonpickle
            with suppress(Exception):
                rc.in_projections['eligible_positions'] = pd.eval(rc.in_projections['eligible_positions'])
            current_projections = current_projections.append(rc.in_projections)
            projections_with_added_players = projections_with_added_players.append(rc.in_projections)
            current_projections.drop(rc.out_player_id, inplace=True)
            needs_sort = True
        if needs_sort:
            current_projections.sort_values(by='fpts', ascending=False, inplace=True)

        game_day_players = current_projections[current_projections.team_id.isin(find_teams_playing(game_day))]
        # print(f"Game Day: {game_day}")
        # print(game_day_players.loc[:,['name', 'eligible_positions', 'team_abbr', 'fpts'] + scoring_categories])
        roster = best_roster(game_day_players.loc[:,['eligible_positions']].itertuples())
        for player in roster:
            projected_games_played[player.player_id] += 1

    return roster_change_set, projections_with_added_players.loc[:,scoring_categories].multiply(pd.Series(projected_games_played), axis=0)
