import pandas as pd 
from datetime import datetime, timedelta

from csh_fantasy_bot.nhl import BestRankedPlayerScorer
from csh_fantasy_bot.league import FantasyLeague


def test_scoring_no_roster_changes(league: FantasyLeague, scoring_weights):
    """Test scoring against known dataset."""
    t = league.to_team('396.l.53432.t.2')
    a_start_date = datetime(2020,2,26)
    all_players = league.as_of(a_start_date)
    date_range = pd.date_range(a_start_date.date(), a_start_date.date() + timedelta(days=7))
    projected_stats = league.get_projections()
    projected_stats['fpts'] = 0
    projected_stats['fpts'] = projected_stats.loc[projected_stats.G == projected_stats.G,scoring_weights.index.tolist()].mul(scoring_weights).sum(1)


    scorer = BestRankedPlayerScorer(league, t, projected_stats)
    # score = scorer.score(date_range)
    pass