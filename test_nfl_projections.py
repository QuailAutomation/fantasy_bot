
import pandas as pd 
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

from csh_fantasy_bot.projections.fantasypros_nfl import get_projections
from csh_fantasy_bot.projections.yahoo_nfl import generate_predictions, PredictionType, retrieve_draft_order


oauth = OAuth2(None, None, from_file='oauth2.json')

f_year = 2022
gm = yfa.Game(oauth, 'nfl')
ids = gm.league_ids(year=f_year)

lg = gm.to_league(ids[2])


yahoo_prediction_fname = f"{f_year}-{lg.league_id}-predictions.csv"

regen_yahoo_projections = True
if regen_yahoo_projections:
    predictions = generate_predictions(lg,predition_type=PredictionType.rest_season)
    # NOTE: currently for preseason the columns in this file are incorrect.  
    # bye should be Bye, and preseason should be overall_rank
    predictions.rename(columns = {'bye':'Bye', 'preseason':'overall_rank'}, inplace = True)
    predictions.to_csv(yahoo_prediction_fname, index=False)


# import pandas as pd
df = pd.read_csv(yahoo_prediction_fname)
df['team'] = df['team'].str.upper()
# print(df.head())

fp_projections = get_projections()
fp_df = pd.DataFrame(fp_projections)
# fp_df = pd.read_csv("/Users/craigh/Downloads/FantasyPros_2021_Draft_ALL_Rankings.csv")

# fp_df.drop('BYE WEEK', axis=1, inplace=True)
# fp_df.rename(columns={"rank": "fp_rank", "POS":"position_rank", "TEAM":'team', 'PLAYER NAME':'name'}, inplace=True)
# some data cleaning
fp_df.loc[fp_df.team == 'JAC','team'] = 'JAX'
fp_df.loc[fp_df.name.str.contains("Mahomes") & (fp_df.team == 'KC'), 'name'] = 'Patrick Mahomes'
fp_df.loc[fp_df.name.str.contains("Chark") & (fp_df.team == 'JAX'), 'name'] = 'DJ Chark Jr.'
fp_df.loc[fp_df.name.str.contains("Darrell Henderson") & (fp_df.team == 'LAR'), 'name'] = 'Darrell Henderson Jr.'
fp_df.loc[fp_df.name.str.contains("Gabriel Davis") & (fp_df.team == 'BUF'), 'name'] = 'Gabe Davis'
fp_df.loc[fp_df.name.str.contains("D.K. Metcalf") & (fp_df.team == 'SEA'), 'name'] = 'DK Metcalf'
fp_df.loc[fp_df.name.str.contains("Ken Walker III") & (fp_df.team == 'SEA'), 'name'] = 'Kenneth Walker III'
fp_df.loc[fp_df.name.str.contains("D.J. Moore") & (fp_df.team == 'CAR'), 'name'] = 'DJ Moore'
fp_df.loc[fp_df.name.str.contains("Josh Palmer") & (fp_df.team == 'LAC'), 'name'] = 'Joshua Palmer'

# for D there is divergence of names.  lets use yahoo names
# index on team so we can rename fantasy pros D name field
select = fp_df.position_rank.str.contains('DST')
fp_df.loc[select,'name'] = fp_df.loc[select, 'team'].map(df[df.position.str.contains('DEF')].set_index('team')['name'].to_dict())

# temp_fp_df = fp_df.set_index('team')
# temp_fp_df['name'] = df[df.position.apply(lambda x: 'D' in x)].set_index('team')['name']

yahoo = df.set_index(['name', 'team'])

fp = fp_df.reset_index().set_index(['name','team'])

combined = yahoo.join(fp)
combined.reset_index(inplace=True)

output_filename = f"{f_year}-{lg.league_id}-predictions-merged.csv"
print(f"can write csv: {output_filename}")
combined.to_csv(output_filename, index=False)
# fp_df[fp_df.position_rank.str.contains('DST')]['name_y'] = yahoo[yahoo.position.apply(lambda x: 'D' in x)]

# temp_fp_df = fp_df[fp_df.position_rank.str.contains('DST')].set_index('team