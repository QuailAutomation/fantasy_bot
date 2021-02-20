from datetime import datetime
import pandas as pd

from csh_fantasy_bot.bot import ManagerBot

# league_id = '403.l.41177'
# league_id = "403.l.18782"
leagues = ['403.l.41177', '403.l.18782']
selected_position = ['C', 'LW', 'RW', 'D']

today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)

for league_id in leagues:
    manager = ManagerBot(league_id=league_id)
    scores = manager.score_team_pulp()

    todays_roster = scores[1].loc[(today,slice(None))].merge(manager.all_players, left_index=True, right_on='player_id')[['name','rostered_position']]
    
    yahoo_roster = pd.DataFrame.from_dict(manager.tm.roster(day=today))
    yahoo_scoring_players = yahoo_roster[yahoo_roster.selected_position.isin(selected_position)].set_index('player_id')
    
    missing_player_ids = todays_roster.index.difference(yahoo_scoring_players.index)
    
    league_name = manager.lg.settings()['name']
    if len(missing_player_ids) > 0:
        print(f"League: {league_name} - Players missing from projected ideal.")
        for player_id in missing_player_ids:
            print(manager.all_players.loc[player_id][['name','status']])
    else:
        print(f'League: {league_name} - Yahoo roster matches projected ideal')