import pandas as pd
import numpy as np

from csh_fantasy_bot import bot
from csh_fantasy_bot.roster_change_optimizer import RosterChangeSet
from csh_fantasy_bot.nhl import score_team

# true value ignores actuals if they exist and works off projections onlyD
simulation_mode=False
week_number = 5
l_id = '419.l.90115'
# league_id = "403.l.18782"
manager = bot.ManagerBot(league_id=l_id, week=week_number, simulation_mode=simulation_mode)
league_scorer = manager.game_week().score_comparer
opp = manager.tm.matchup(week_number)
print(f'Opponent: {manager._get_team_name(manager.lg, opp)}')


# paste roster change text into here
"""
Here is example of what roster change text should look like
It is output from the rosterchangeset.pretty_print method

Date: 2022-10-30, in: Cole Perfetti(8650), out: Justin Faulk(5010)
Date: 2022-10-24, in: Ondrej Palat(5573), out: Tanner Jeannot(7365)
Date: 2022-10-24, in: Dmitry Orlov(5254), out: Colin White(6763)
Date: 2022-10-28, in: Jakub Voracek(4246), out: Ryan O'Reilly(4786)
"""
roster_change_text="""

"""

roster_changes = RosterChangeSet.from_pretty_print_text(roster_change_text, manager.game_week(week_number).all_player_predictions)

scores_with_changes = manager.score_team(roster_change_set=roster_changes)[1]
scoring_result = league_scorer.score(scores_with_changes)[manager.stat_categories]
print(scoring_result)
print(f"\nScore: opp->({scoring_result.loc['score_opp'].sum()}), league->({scoring_result.loc['score_league'].sum()})") 
if (roster_change_text != ''):
    scores_ignore_roster_changes = manager.score_team()[1]
    score_result_no_changes = league_scorer.score(scores_ignore_roster_changes)
    print (f"\nWithout roster changes: opp->({score_result_no_changes.loc['score_opp'].sum()}), league->({score_result_no_changes.loc['score_league'].sum()})") 
    