import pandas as pd
import numpy as np

from csh_fantasy_bot import bot

simulation_mode=False
week_number = 9
l_id = '411.l.85094'
# league_id = "403.l.18782"
manager = bot.ManagerBot(league_id=l_id, week=week_number, simulation_mode=simulation_mode)
league_scorer = manager.game_week().score_comparer

predictions = manager.game_week().all_player_predictions
print(predictions.head())

def display_sort_ftps(df, ascending=False):
    return df.sort_values('fpts', ascending=ascending)[['name','eligible_positions', 'status','fantasy_status','fpts']]

rest_season_predictions = manager.game_week().all_player_predictions

my_team = rest_season_predictions[rest_season_predictions.fantasy_status == 8]
print(display_sort_ftps(my_team))

print(my_team[['name', 'eligible_positions', 'G', 'A', 'HIT', 'SOG','fantasy_status', 'fpts']])