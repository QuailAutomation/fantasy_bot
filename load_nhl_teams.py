import pandas as pd

url = 'https://statsapi.web.nhl.com/api/v1/teams'

# Load the first sheet of the JSON file into a data frame
df = pd.read_json(r'/Users/craigh/dev/yahoo_fantasy_bot/nhl.teams.json')

# View the first ten rows
#print(df.head(10))

print('done')

# load teams
# load schedule for canucks
# load box score for each game so far

# https://statsapi.web.nhl.com/api/v1/game/2019020001/boxscore

from nhl_scraper import nhl
# box score sens vs leafs
#sens_vs_leafs = pd.read_json('sens_leafs.json')
#print(sens_vs_leafs.head())

nhl = nhl.Scraper()
teams = nhl.teams()
print(teams.head(10))
#sens_goals = sum(sens_vs_leafs())

player_list = nhl.players()
print(player_list.head(10))
pass