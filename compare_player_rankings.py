import os
import json
from csh_fantasy_bot import bot
from get_docker_secret import get_docker_secret
from yahoo_oauth import OAuth2


week_number = 21

manager: bot.ManagerBot = None
if 'YAHOO_OAUTH_FILE' in os.environ:
    auth_file = os.environ['YAHOO_OAUTH_FILE']
    manager = bot.ManagerBot(week_number,oauth_file=auth_file)
else:
    manager = bot.ManagerBot(week_number)


all_players = manager.all_players
print("Num players is: {}".format(len(all_players)))
