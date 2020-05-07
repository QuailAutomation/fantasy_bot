import pandas as pd

from csh_fantasy_bot.ga import RandomWeightedSelector

# def normalize(df, column, inverse=False):
#     if inverse:
#         #  df[f'{column}-normalized'] = (df[column].sum() / (df[column] + 1))
#         df[f'{column}-normalized'] = 1 - (df[column] / df[column].sum()) 
#         df[f'{column}-normalized'] = df[f'{column}-normalized']/df[f'{column}-normalized'].sum()  
#         # (frame.WEIGHT.sum() / (frame.WEIGHT + 1))
#     else:
#         df[f'{column}-normalized'] = df[column]/df[column].sum()

def test_weighted_sampling(league, season_start_date):
    """Do weighted random sample of fpts."""
    all_players = league.as_of(season_start_date)
    stats = ["G", "A", "+/-", "PIM", "SOG", "FW", "HIT"]
    weights_series =  pd.Series([1, .75, 1, .5, 1, .1, 1], index=stats)
    projected_stats = league.get_projections()
    projected_stats['fpts'] = 0
    players_with_projections = projected_stats[projected_stats.G == projected_stats.G]
    players_with_projections = players_with_projections[projected_stats.fantasy_status == 2]
    players_with_projections['fpts'] = players_with_projections.loc[:,stats].mul(weights_series).sum(1)

    selector = RandomWeightedSelector(players_with_projections, 'fpts', inverse=True)

    # for player in selector.select():
    #     print(player)

    
    
    pass
    