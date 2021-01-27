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
# from csh_fantasy_bot.league import FantasyLeague

import cProfile


nhl_schedule = {}
nhl_scraper: Scraper = Scraper()

my_leagues = {}

log = logging.getLogger(__name__)
DATE_FORMAT = "%Y-%m-%d"
def find_teams_playing(game_day=None, num_days=1):
    """Get list of teams playing on game_day."""
    global nhl_schedule
    global nhl_scraper
    end_date = game_day + datetime.timedelta(days=num_days -1)

    return nhl_scraper.games_count(game_day, end_date)
        

# add elements of tuple - tuple(x+y for x, y in zip(a,b))


def _league_id_from_team_key(team_key):
    """Extract the league key from the passed in team_key.

    Args:
        team_key (string): The yahoo fantasy team key
    
    Returns:
        string: yahoo league key
    """
    return ".".join(team_key.split('.')[:-2])

def _roster_changes_as_day_dict(rcs):
    rc_dict = defaultdict(list)
    if rcs:
        for rc in rcs.roster_changes:
            rc_dict[rc.change_date].append(rc) 
    
    return rc_dict

def score_team(player_projections, date_range, scoring_categories, roster_change_set=None, simulation_mode=True, date_last_use_actuals=None, team_id=None):
    """Score the team.

    Args:
        player_projections (DataFrame): Projections for all players on the team
        date_range (pd.DateRange): Date range to project for
        scoring_categories (list): List of player scoring categories scored
        roster_change_set (RosterChangeSet, optional): Changes to make throughout the scoring period. Defaults to None.
        simulation_mode (bool, optional): Ignores actuals if games already played, still uses projected scoring. Defaults to True.
        date_last_use_actuals (DateTime): If not in simulation mode, this value sets the last day to use actual scoring instead of projecting. 
        team_id (string, optional): Need this to look up actual scores for days which have passed.

    Returns:
        [type]: [description]
    """
    # we are going to modify this as we iterate the dates.  so we need this for the math at end
    current_projections = player_projections.copy()
    # projections for players who may play.  changes with roster changes during period
    projections_with_added_players = player_projections.copy()
    current_projections.sort_values(by='fpts', ascending=False, inplace=True)
    # dict to keep track of how many games players play using projected stats
    projected_games_played = defaultdict(int)
    # we need to look up roster changes by date so let's make a dict ourselves
    rc_dict = _roster_changes_as_day_dict(roster_change_set)
    
    if not (simulation_mode or date_last_use_actuals):
        # if date_last_use_actuals is not set, we default it to today
        date_last_use_actuals = datetime.datetime.today()

    for game_day in date_range:
        if not simulation_mode and game_day <= date_last_use_actuals:
            # let's see if we should grab actuals
            # load actuals
            log.info(f"Look up actuals for: {team_id}-{game_day}")
            league_id = _league_id_from_team_key(team_id)
            if league_id not in my_leagues:
                my_leagues[league_id] = FantasyLeague(league_id=league_id)
            
            pass
        else:
            for rc in rc_dict[game_day.date()]:
                # TODO should really figure out how to deal with this.  sometimes it is string, sometimes list. 
                # i think has to do with serializing via jsonpickle
                with suppress(Exception):
                    rc.in_projections['eligible_positions'] = pd.eval(rc.in_projections['eligible_positions'])
                # add player in projections to projection dataframe
                current_projections = current_projections.append(rc.in_projections)
                projections_with_added_players = projections_with_added_players.append(rc.in_projections)
                current_projections.drop(rc.out_player_id, inplace=True)
                current_projections.sort_values(by='fpts', ascending=False, inplace=True)

            game_day_players = current_projections[current_projections.team_id.isin(find_teams_playing(game_day))]
            roster = best_roster(game_day_players.loc[:,['eligible_positions']].itertuples())
            for player in roster:
                projected_games_played[player.player_id] += 1

    #TODO maybe we should formalize a return structure
    return roster_change_set, projections_with_added_players.loc[:,scoring_categories].multiply(pd.Series(projected_games_played), axis=0)




# if single_date < today.date() and not simulation_mode:
#                 if single_date not in self.cached_actual_results:
#                     # retrieve actual results
#                     the_roster = self.team.roster(day=single_date)
#                     daily_roster = pd.DataFrame(the_roster)
#                     lineup = daily_roster.query('selected_position != "BN" & selected_position != "G"')
#                     stats = self.league.player_stats(lineup.player_id.tolist(), "date", date=single_date)
#                     lineup.set_index('player_id', inplace=True)
#                     daily_stats = pd.DataFrame(stats).loc[:,['player_id'] + self.tracked_stats]
#                     daily_stats.set_index('player_id', inplace=True)
#                     daily_stats = daily_stats.merge(lineup['selected_position'], left_index=True, right_index=True)
#                     daily_stats.loc[:,'score_type'] = 'a'
#                     daily_stats.replace('-', np.nan, inplace=True)
#                      self.cached_actual_results[single_date] = daily_stats.loc[~daily_stats.G.isnull(),:]
#                  daily_scoring_results = self.cached_actual_results[single_date]