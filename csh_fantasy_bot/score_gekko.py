import time
from math import e
from collections import defaultdict

import numpy as np
from contextlib import suppress

from gekko import GEKKO

from nhl_scraper.nhl import Scraper
import pandas as pd


nhl_scraper = Scraper()

# available_positions = {
#         "C":2,
#         "LW":2,
#         "RW":2,
#         "D":4,
#     }

def _roster_changes_as_day_dict(rcs):
    rc_dict = defaultdict(list)
    if rcs:
        for rc in rcs.roster_changes:
            rc_dict[rc.change_date].append(rc) 
    
    return rc_dict

def score_gekko(team_projections, team_id, opponent_scoring, scoring_categories, date_range, roster_makeup, date_last_use_actuals=None, roster_change_set=None, actual_scores=None):

  # if we don't have any actuals, lets return 0 for all stats
  if actual_scores is None:
    actual_scores = defaultdict(lambda:0)

  m = GEKKO(remote=False, server='http://localhost:8083')
  m.options.SOLVER = 1

  # with roster changes we make changes, so let's copy the projections
  current_projections = team_projections.copy()
  # projections for players who may play.  changes with roster changes during period
  projections_with_added_players = team_projections.copy()

  rewards=defaultdict(list)
  player_vars = defaultdict(dict)

  rc_dict = defaultdict(list)
  if roster_change_set:
      rc_dict = _roster_changes_as_day_dict(roster_change_set)

  for game_day_idx, game_day in enumerate(date_range):
    for rc in rc_dict[game_day.date()]:
      # TODO should really figure out how to deal with this.  sometimes it is string, sometimes list. 
      # i think has to do with serializing via jsonpickle
      with suppress(Exception):
          rc.in_projections['eligible_positions'] = pd.eval(rc.in_projections['eligible_positions'])
      # add player in projections to projection dataframe
      current_projections = current_projections.append(rc.in_projections)
      projections_with_added_players = projections_with_added_players.append(rc.in_projections)
      current_projections.drop(rc.out_player_id, inplace=True)
      # current_projections.sort_values(by='fpts', ascending=False, inplace=True)

    teams_playing_today = nhl_scraper._teams_playing_one_day(game_day.to_pydatetime().date())
    game_day_players = current_projections[current_projections.team_id.isin(teams_playing_today)]
    scores = {}
    players = {}
    for position in roster_makeup.keys():
      available_for_position = game_day_players[game_day_players.eligible_positions.map(set([position]).issubset)]
      if len(available_for_position) > 0:
        players[position]= list(available_for_position.index)
        scores[position] = available_for_position[scoring_categories]

    vars_by_player = defaultdict(list)
    for position in players:
      for player in players[position]:
        player_var = m.Var(1,0,1,True,name=f"{game_day_idx}_{position}_{player}")
        if position not in player_vars[game_day_idx]:
          player_vars[game_day_idx][position] = []
        player_vars[game_day_idx][position].append(player_var)
        vars_by_player[player].append(player_var)
        for category in scoring_categories:
          rewards[category].append(player_var * game_day_players.loc[player,category])
      # limit amount players to roster size allowed for position
      if position in player_vars[game_day_idx]:
        m.Equation(m.sum(player_vars[game_day_idx][position]) <= roster_makeup[position])
    
      

    # for players with multiple eligible positions, make sure only appear once
    for player_id, player_info in game_day_players.iterrows():
      eligible_positions = player_info.eligible_positions
      if len(eligible_positions) > 1:
          m.Equation(m.sum(vars_by_player[player_id]) <= 1)

  for category in scoring_categories:
    m.Obj(-1 * (1 / (1 + e ** (-(m.sum(rewards[category]) + actual_scores[category] - opponent_scoring[category])))))

  result = None
  try:  
    m.solve(disp=False)
  except Exception as ex:
    print('Exception')
    time.sleep(1)
    m.solve()
    

  rostered_players = []
  for game_day_idx, game_day in enumerate(date_range):
    for position in roster_makeup.keys():
      if position in player_vars[game_day_idx]:
        for player in player_vars[game_day_idx][position]:
          if player.value[0] == 1:
            attrs = player.name.split("_")
            player_id = int(attrs[-1])
            position = player.name.split("_")[-2].upper()
            rostered_players.append([player_id, position, 'p',game_day])
  results = pd.DataFrame(rostered_players, columns=['player_id', 'rostered_position', 'score_type', 'play_date'])
  results = results.join(projections_with_added_players[scoring_categories], on='player_id')
  return results


if __name__ == "__main__":
  pass
    # manager = ManagerBot(week=5, league_id='403.l.41177')
    # scoring_categories = manager.stat_categories
    # manager.as_of(manager.week[0])
    # opponent_scoring = manager.opponent.scores()[scoring_categories].sum()
    # all_players = manager.lg.get_projections()
    # my_roster = all_players[(all_players.fantasy_status == 2) 
    #                 & ((all_players.status != 'IR') 
    #                 & (all_players.status != 'IR-LT'))]

    # score_gekko(my_roster,"team",opponent_scoring,scoring_categories,manager.week,None)