import logging
import pandas as pd
from csh_fantasy_bot import automation


logging.basicConfig(level=logging.INFO)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

driver = automation.Driver()
driver.run()