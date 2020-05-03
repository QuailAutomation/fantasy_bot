import pandas as pd
import logging

class ScoreComparer:
    """
    Class that compares the scores of two lineups.
     
    Computes whether it is *better* (in the fantasy sense).

    :param cfg: Configparser object
    :param scorer: Object that computes scores for the categories
    :param lg_lineups: All of the lineups in the league.  This is used to
        compute a standard deviation of all of the stat categories.
    """
    def __init__(self, lg_lineups, player_projections, stat_categories):
        self.opp_sum = None
        self.stdev_cap = .2
        self.stat_cats = stat_categories
        self.player_projections = player_projections
        self.stdevs = self._compute_agg(lg_lineups, 'std')
        self.league_means = self._compute_agg(lg_lineups, 'mean')
        self.log = logging.getLogger(__name__)

    def set_opponent(self, opp_sum):
        """
        Set the stat category totals for the opponent.

        :param opp_sum: Sum of all of the categories of your opponent
        """
        self.opp_sum = pd.Series(opp_sum)

    def compute_score(self, score_sum):
        """
        Calculate a lineup score by comparing it against the standard devs.

        :param lineup: Lineup to compute standard deviation from
        :return: Standard deviation score
        """
        try:
            my_scores = score_sum.loc[:, self.stat_cats].sum()
        except IndexError as e:
            self.log.exception(e)
        assert(self.opp_sum is not None), "Must call set_opponent() first"
        assert(self.stdevs is not None)
        means = pd.DataFrame([my_scores,self.opp_sum]).mean()
        diff = (my_scores - means)/means
        return diff.clip(lower=-1 * self.stdev_cap, upper=self.stdev_cap).sum()


    def print_stdev(self):
        print("Standard deviations for each category:")
        for cat, val in self.stdevs.iteritems():
            print("{} - {:.3f}".format(cat, val))
        print("")

    def _compute_agg(self, lineups, agg):
        """
        Compute an aggregation of each of the categories.

        :param lineups: Lineups to compute the aggregation on
        :return: Aggregation compuation for each category
        :rtype: DataFrame
        """
        scores = pd.DataFrame()
        for lineup in lineups:
            if type(lineup) is pd.DataFrame:
                df = pd.DataFrame(data=lineup, columns=lineup.columns)
            else:
                df = pd.DataFrame(data=lineup, columns=lineup[0].index)

            scores = scores.append(df.loc[:,self.stat_cats].sum(), ignore_index=True)
        return scores.agg([agg]).loc[agg,:]

    def print_week_results(self, my_scores_summary):
        scoring_stats = my_scores_summary.sum().loc[self.stat_cats]
        opp_scoring_stats = self.opp_sum.loc[self.stat_cats]
        sc = self.compute_score(my_scores_summary)
        differences = scoring_stats - opp_scoring_stats

        means = pd.DataFrame([scoring_stats, opp_scoring_stats]).mean()
        # differences / means
        score = differences / means
        cat_win_loss = score.mask(score < 0, -1)
        cat_win_loss = cat_win_loss.mask(cat_win_loss > 0, 1)
        # cat_win = 1 if my_scores.sum() > manager.score_comparer.opp_sum else -1
        # TODO handle tie as within threshold, which would depend on the stat
        summary_df = pd.DataFrame(
            [scoring_stats, opp_scoring_stats, differences, means, self.league_means,
             self.stdevs, differences/self.stdevs, score,cat_win_loss],
            index=['my-scores', 'opponent', 'difference', 'mean-opp', 'mean-league', 'std dev', 'num_stds', 'score','win_loss'])
        print(summary_df.head(10))
        print("Score: {:4.2f}".format(sc))