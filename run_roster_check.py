from datetime import datetime, timedelta
import pandas as pd

from csh_fantasy_bot.bot import ManagerBot

leagues = ['403.l.41177', '403.l.18782']

# TODO should ignore players designated out if they are not on yahoo roster

for league_id in leagues:
    manager = ManagerBot(league_id=league_id)
    day = datetime.today() + timedelta(days=1)
    returnVal = manager.compare_roster_yahoo_ideal(day)    
    print(returnVal)
    