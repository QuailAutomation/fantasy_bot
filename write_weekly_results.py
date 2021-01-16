import pandas as pd
import numpy as np
from datetime import datetime, timezone

from yahoo_fantasy_api import League
from csh_fantasy_bot import bot, nhl, roster_change_optimizer

import logging
logging.basicConfig(level=logging.INFO)

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

from elasticsearch import Elasticsearch
from elasticsearch import helpers

week_number = 19

es = Elasticsearch(hosts='http://192.168.1.20:9200', http_compress=True)

manager: bot.ManagerBot = bot.ManagerBot(league_id="403.l.18782") #league_id=266295

league :League  = manager.lg


pass