import pandas as pd

def retrieve_yahoo_projections(league_id, scored_categories):
    prediction_csv = f'yahoo-projections-stats-{league_id}.csv'
    predictions = pd.read_csv(prediction_csv,
                        converters={"eligible_positions": lambda x: x.strip("[]").replace("'", "").split(", ")})
    predictions['league_id'] = league_id
    predictions.rename(columns={"id": "player_id"}, inplace=True)
    predictions.set_index('player_id', inplace=True)

    d_scored_categories = scored_categories.copy()
    # if FW are in cats, let's ignore them for D.  Keeps D fantasy score close relative to F 
    try:
        d_scored_categories.remove('FW')
    except ValueError:
        pass
    
    def produce_csh_ranking(predictions, scoring_categories, selector):
        """Create ranking by summing standard deviation of each stat, summing, then dividing by num stats."""
        f_mean = predictions.loc[selector,scoring_categories].mean()
        f_std =predictions.loc[selector,scoring_categories].std()
        f_std_performance = (predictions.loc[selector,scoring_categories] - f_mean)/f_std
        for stat in scoring_categories:
            predictions.loc[selector, stat + '_std'] = (predictions[stat] - f_mean[stat])/f_std[stat]
        
        predictions.loc[selector, 'fantasy_score'] = f_std_performance.sum(axis=1)/len(scoring_categories)
        return predictions

    # the bulk importer for ES can't handled NAN, so let's initialize to 0
    for stat in scored_categories:
            predictions.loc[:, stat + '_std'] = 0
    produce_csh_ranking(predictions, scored_categories, predictions['position'] != 'D')
    produce_csh_ranking(predictions, d_scored_categories, predictions['position'] == 'D')
    # predictions.sort_values('fantasy_score', inplace=True,ascending=False)
    sorted_predictions = predictions.reset_index().sort_values('fantasy_score', ascending=False, ignore_index=True)
    sorted_predictions['csh_rank'] = sorted_predictions.index + 1
    
    return sorted_predictions