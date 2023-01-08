import pandas as pd
import nfl_data_py as nfl

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

draft = nfl.import_draft_picks([2022])

print(draft.loc[draft.position.isin(['RB', 'WR']),['round', 'pick', 'position', 'team', 'pfr_player_name', 'age']])

print(draft.loc[11670])