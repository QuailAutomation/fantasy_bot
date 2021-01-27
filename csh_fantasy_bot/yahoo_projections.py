import pandas as pd

yahoo_projections = {}

def retrieve_yahoo_rest_of_season_projections(league_id):
    if league_id not in yahoo_projections:
        prediction_csv = f'.cache/{league_id}/yahoo-projections-stats.csv'
        predictions = pd.read_csv(prediction_csv,
                            converters={"eligible_positions": lambda x: x.strip("[]").replace("'", "").split(", ")})
        predictions['league_id'] = league_id
        predictions.rename(columns={"id": "player_id"}, inplace=True)
        predictions.set_index('player_id', inplace=True)
        yahoo_projections[league_id] = predictions

    return yahoo_projections[league_id]

def produce_csh_ranking(predictions, scoring_categories, selector):
        """Create ranking by summing standard deviation of each stat, summing, then dividing by num stats."""
        f_mean = predictions.loc[selector,scoring_categories].mean()
        f_std =predictions.loc[selector,scoring_categories].std()
        f_std_performance = (predictions.loc[selector,scoring_categories] - f_mean)/f_std
        for stat in scoring_categories:
            predictions.loc[selector, stat + '_std'] = (predictions[stat] - f_mean[stat])/f_std[stat]
        
        predictions.loc[selector, 'fantasy_score'] = f_std_performance.sum(axis=1)/len(scoring_categories)
        return predictions

def _actuals_for_team_day(self, team_id, game_day, scoring_categories):
        the_roster = self.team_by_key(team_id).roster(day=game_day)
        opp_daily_roster = pd.DataFrame(the_roster)
        lineup = opp_daily_roster.query('selected_position != "BN" & selected_position != "G"')
        stats = self.player_stats(lineup.player_id.tolist(), "date", date=game_day)
        daily_stats = pd.DataFrame(stats).loc[:,['player_id'] + scoring_categories]
        daily_stats.loc[:,'score_type'] = 'a'
        daily_stats.replace('-', np.nan, inplace=True)
        daily_stats.set_index('player_id',inplace=True)
        time.sleep(.5)
        return daily_stats.loc[~daily_stats.G.isnull(),:]
        