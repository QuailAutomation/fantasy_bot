import datetime
import logging
import pandas as pd

from csh_fantasy_bot import bot

player_stats = ["G", "A", "+/-", "PIM", "SOG", "FW", "HIT"]

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

logger = logging.getLogger(__name__)

game_week = 11
bot = bot.ManagerBot(game_week)

# what are days for this week matchup
(week_start,week_end) = bot.lg.week_date_range(game_week)
week = pd.date_range(week_start, week_end)
# get opponent
opp_team_key = bot.tm.matchup(game_week)
opp_team = bot.lg.to_team(opp_team_key)
# for days in week that have passed, lets load roster used and find stats
today = datetime.datetime.now()


def get_team_results(team):
    opp_daily_rosters = pd.DataFrame()
    for game_day in week:
        if today > game_day:
            opp_daily_roster = pd.DataFrame(team.roster(day=game_day))
            lineup = opp_daily_roster.query('selected_position != "BN" & selected_position != "G"')
            stats = bot.lg.player_stats(lineup.player_id.tolist(), "date", date=game_day)
            daily_stats = pd.DataFrame(stats)
            daily_stats['date'] = game_day
            opp_daily_rosters = opp_daily_rosters.append(daily_stats[daily_stats.GP != '-'])
    return opp_daily_rosters

# pd.DataFrame(my_results, columns=player_stats)
opp_results = get_team_results(opp_team)
my_results = get_team_results(bot.tm)
print(opp_results.sum())
print(my_results.sum())

print("Results: {}".format(my_results.subtract(opp_results, axis=1)))