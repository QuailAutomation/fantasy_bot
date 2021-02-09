import logging
import pandas as pd 
import numpy as np

from collections import defaultdict

logging.getLogger().setLevel(level=logging.INFO)
logging.getLogger("yahoo_oauth").setLevel(level=logging.INFO)


from csh_fantasy_bot.bot import ManagerBot
from nhl_scraper.nhl import Scraper
from csh_fantasy_bot.scoring import ScoreComparer

from pulp import *

league_id = '403.l.41177'
week_number = 3
#  zero based (Mon = 0, to x)
game_day_week = 1
manager = ManagerBot(week_number, league_id=league_id)

my_scores = manager.my_team.scores()
# manager.score_comparer.print_week_results(my_scores)

nhl_scraper = Scraper()

# lets do second day of week, lots of guys can play
game_day = manager.week[game_day_week]
teams_playing_today = nhl_scraper._teams_playing_one_day(game_day.to_pydatetime().date())
my_roster = manager.my_team.roster().copy()
game_day_players = my_roster[my_roster.team_id.isin(teams_playing_today)]

game_day_players.head()
game_day_players = game_day_players[["eligible_positions", "name"] + manager.stat_categories]
game_day_players.head(20)

opponent_scores = manager.opponent.scores()
opponent_scores_for_day = opponent_scores[opponent_scores.play_date == game_day]

my_scores = manager.my_team.scores()
my_scores_for_day = my_scores[my_scores.play_date == game_day]

scorer = ScoreComparer(manager.projected_league_scores.values(),manager.stat_categories)
scorer.opp_sum = opponent_scores_for_day.sum()

result = scorer.compute_score(game_day_players)

player_ids = game_day_players.index.values

available_positions = {
    "C":2,
    "LW":2,
    "RW":2,
    "D":4,
}

scoring_max_diff = {
    'G': 4,
    'A': 8,
    '+/-': 5,
    'PIM': 10,
    'SOG': 10,
    'HIT': 10,
    'FW': 10
}

scores = {}
players = {}

for position in available_positions.keys():
    available_for_position = game_day_players[game_day_players.eligible_positions.map(set([position]).issubset)]
    players[position]= list(available_for_position.index)
    scores[position] = available_for_position[manager.stat_categories]

# for day in manager.week:
#     teams_playing_today = nhl_scraper._teams_playing_one_day(day.to_pydatetime().date())
#     game_day_players = my_roster[my_roster.team_id.isin(teams_playing_today)]


variables = {position: LpVariable.dict(position, players[position], cat="Binary")
             for position in players}

prob = pulp.LpProblem('Roster', LpMaximize)

rewards = defaultdict(list)

for position, players in variables.items():
    for player, player_selected in players.items():
        for cat in manager.stat_categories:
            rewards[cat] += scores[position].loc[player, cat] * player_selected
        
    prob += (lpSum(players.values()) <= available_positions[position])

# for each player that has multiple eligible positions, make sure only used once
for player_id, player_info in game_day_players.iterrows():
    eligible_positions = player_info.eligible_positions
    
    if len(eligible_positions) > 1:
        prob += (lpSum([variables[eligible_position][player_id] for eligible_position in eligible_positions]) <= 1)
    

opponent_scoring_summary = opponent_scores_for_day.sum()

objective = []
for stat in manager.stat_categories:
    objective += np.clip(rewards[stat] - opponent_scoring_summary[stat], -1 * scoring_max_diff[stat], scoring_max_diff[stat])

prob += lpSum(objective) 


status = prob.solve()

optimized_roster = pd.DataFrame()
for var in prob.variables():
    if pulp.value(var):
        position, player_id  = var.name.split('_')
        player_id = int(player_id)
        optimized_roster = optimized_roster.append(game_day_players.loc[player_id, manager.stat_categories])
        print(f'{position} - {game_day_players.loc[player_id, "name"]}')
    

print(status)