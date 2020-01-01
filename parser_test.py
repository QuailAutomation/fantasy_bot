from csh_fantasy_bot import fantasysp_scrape
import pandas as pd

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

# p = fantasysp_scrape.Parser(positions=['G'])
p = fantasysp_scrape.Parser()