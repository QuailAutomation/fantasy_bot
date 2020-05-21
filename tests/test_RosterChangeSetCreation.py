from datetime import timedelta
import pandas as pd

from csh_fantasy_bot.ga import RosterChangeSetFactory


def test_create_rcs(league, season_start_date, scoring_weights):

    date_range = pd.date_range(season_start_date, season_start_date + timedelta(days=6))
    all_players = league.as_of(season_start_date).all_players()
    projected_stats = league.get_projections()
    
    projected_stats['fpts'] = 0
    # players_with_projections = projected_stats[projected_stats.G == projected_stats.G]
    # players_with_projections = players_with_projections[projected_stats.fantasy_status == 2]
    projected_stats['fpts'] = projected_stats.loc[projected_stats.G == projected_stats.G,scoring_weights.index.tolist()].mul(scoring_weights).sum(1)


    factory = RosterChangeSetFactory(projected_stats, 2, date_range, 4)
    changes = []
    for _ in range(100):
        changes.append(factory.createChromosome())
    pass