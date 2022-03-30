from csh_fantasy_bot.data.all import *

# player_predictions = manager.game_week().all_player_predictions
# ir_selector = player_predictions.eligible_positions.map(set(['IR']).issubset)
# addable_players = (player_predictions.fantasy_status != 'FA') & (player_predictions.fantasy_status != 'W') & ~(ir_selector)
fdata = FantasyData()
players = fdata.all_players
draft = fdata.draft_results
predictions = fdata.player_projections()
# predictions = fdata.predictions.7
# predictions = fdata.predictions.14
# predictions = fdata.predictions.rest_season
print(fdata.scoring_categories)

select = fdata.selectors
# addable_players = projected_stats[ (projected_stats.fantasy_status == 'FA') & 
#                                         (projected_stats.status != 'O') &
#                                         (projected_stats.fantasy_status != my_team_id) & 
#                                         (projected_stats.percent_owned > 5)]

addable_players = predictions[select.fa]
pass