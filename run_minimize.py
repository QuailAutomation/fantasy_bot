from math import e
from collections import defaultdict
import numpy as np

from csh_fantasy_bot.bot import ManagerBot
from nhl_scraper.nhl import Scraper
from csh_fantasy_bot.roster_change_optimizer import RosterChangeSet


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
