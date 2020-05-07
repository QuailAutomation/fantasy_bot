from csh_fantasy_bot.celery_app import init_celery
celery = init_celery()
from csh_fantasy_bot.tasks import *
import pandas as pd
import jsonpickle
from csh_fantasy_bot.roster_change_optimizer import RosterChangeSet
dates = pd.date_range('2020-2-24', '2020-3-1')
changes = []
rc = RosterChangeSet(dates)
rc.add(6376, 1600, dates[1])``
changes.append(rc)
rc = RosterChangeSet(dates)
rc.add(5698, 3266,dates[2])
changes.append(rc)

rc_jp = jsonpickle.encode(changes)
