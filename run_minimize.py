from math import e
from collections import defaultdict
import numpy as np

from gekko import GEKKO

from csh_fantasy_bot.bot import ManagerBot
from nhl_scraper.nhl import Scraper
from csh_fantasy_bot.roster_change_optimizer import RosterChangeSet

m = GEKKO(remote=True)
m.options.SOLVER = 1

nhl_scraper = Scraper()

available_positions = {
        "C":2,
        "LW":2,
        "RW":2,
        "D":4,
    }

manager = ManagerBot(week=5, league_id='403.l.41177')
roster_change_text="""
Date: 2021-02-19, in: Brock Nelson(4990), out: Nazem Kadri(3637)
"""
roster_changes = RosterChangeSet.from_pretty_print_text(roster_change_text, manager.all_player_predictions)

scores_with = manager.score_team_pulp(roster_change_set=roster_changes)
scores_without = manager.score_team_pulp()

scoring_categories = manager.stat_categories
manager.as_of(manager.week[0])
opponent_scoring = manager.opponent.scores()[scoring_categories].sum()
all_players = manager.lg.get_projections()
my_roster = all_players[(all_players.fantasy_status == 2) 
                & ((all_players.status != 'IR') 
                & (all_players.status != 'IR-LT'))]

def score_gekko():
  rewards=defaultdict(list)
  vars = defaultdict(dict)
  for game_day_idx, game_day in enumerate(manager.week):
    teams_playing_today = nhl_scraper._teams_playing_one_day(game_day.to_pydatetime().date())
    game_day_players = my_roster[my_roster.team_id.isin(teams_playing_today)]
    scores = {}
    players = {}
    for position in available_positions.keys():
      available_for_position = game_day_players[game_day_players.eligible_positions.map(set([position]).issubset)]
      players[position]= list(available_for_position.index)
      scores[position] = available_for_position[scoring_categories]

    vars_by_player = defaultdict(list)
    for position in players:
      for player in players[position]:
        player_var = m.Var(1,0,1,True,name=f"{game_day_idx}_{position}_{player}")
        if position not in vars[game_day_idx]:
          vars[game_day_idx][position] = []
        vars[game_day_idx][position].append(player_var)
        vars_by_player[player].append(player_var)
        for category in scoring_categories:
          rewards[category].append(player_var * game_day_players.loc[player,category])
      # limit amount players to roster size allowed for position
      if position in vars[game_day_idx]:
        m.Equation(m.sum(vars[game_day_idx][position]) <= available_positions[position])
      

    # for players with multiple eligible positions, make sure only appear once
    for player_id, player_info in game_day_players.iterrows():
      eligible_positions = player_info.eligible_positions
      if len(eligible_positions) > 1:
          m.Equation(m.sum(vars_by_player[player_id]) <= 1)

  for category in scoring_categories:
    m.Obj(-1 * (1 / (1 + e ** (-(m.sum(rewards[category]) - opponent_scoring[category])))))
  result = m.solve(disp=True)

  print(f'Done, score: {m.options.OBJFCNVAL * -1}')
# print(f'Score: {team_score(my_team)}')

score_gekko()