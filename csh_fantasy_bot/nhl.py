import datetime
import pandas as pd
import numpy as np
import logging
from nhl_scraper.nhl import Scraper
from nhl_scraper.rotowire import Scraper as RWScraper
from yahoo_fantasy_api import League, Team
from csh_fantasy_bot import roster

import cProfile


class BestRankedPlayerScorer:
    nhl_schedule = {}

    def __init__(self, league, team, player_projections):
        self.log = logging.getLogger(__name__)
        self.league = league
        self.tracked_stats = league.scoring_categories()
        self.league_edit_date = league.edit_date()
        self.team = team

        self.player_projections = player_projections
        self.nhl_scraper: Scraper = Scraper()
        self.cached_actual_results = {}
        # self.starting_goalies_df = RWScraper().starting_goalies()
        # if there are no projections available, we will load from yahoo, and cache here
        self.cached_player_stats = {}
        # cache rosters we load
        self.cached_roster_stats = {}
        self.roster_builder = roster.RecursiveRosterBuilder()

    def score(self, date_range, roster_change_set=None, results_printer=None, simulation_mode=True):
        """Score the roster for the week.

        simulation_mode=True will never use actuals, just use projections.
        """
        roster_df = None
        today = pd.Timestamp.today()
        projected_week_results = None
        for single_date in date_range:
            daily_scoring_results = None
            the_roster = None
            if single_date < today.date() and not simulation_mode:
                if single_date not in self.cached_actual_results:
                    # retrieve actual results
                    the_roster = self.team.roster(day=single_date)
                    daily_roster = pd.DataFrame(the_roster)
                    lineup = daily_roster.query('selected_position != "BN" & selected_position != "G"')
                    stats = self.league.player_stats(lineup.player_id.tolist(), "date", date=single_date)
                    lineup.set_index('player_id', inplace=True)
                    daily_stats = pd.DataFrame(stats).loc[:,['player_id'] + self.tracked_stats]
                    daily_stats.set_index('player_id', inplace=True)
                    daily_stats = daily_stats.merge(lineup['selected_position'], left_index=True, right_index=True)
                    daily_stats.loc[:,'score_type'] = 'a'
                    daily_stats.replace('-', np.nan, inplace=True)

                    self.cached_actual_results[single_date] = daily_stats.loc[~daily_stats.G.isnull(),:]
                daily_scoring_results = self.cached_actual_results[single_date]
            else:
                if (roster_df is None or single_date <= self.league_edit_date) and not simulation_mode: 
                    if single_date not in self.cached_roster_stats:
                        # roster_df = pd.DataFrame(self.team.roster(day=single_date))
                        roster_df =self.player_projections[self.player_projections['fantasy_status'] == int(self.team.team_key.split('.')[-1])]
                        # roster_df.set_index('player_id', inplace=True)
                        self.cached_roster_stats[single_date] = roster_df

                    roster_df = self.cached_roster_stats[single_date]
                
                    days_from_today = single_date - today
                    # if within 3 days of today, let's remove OUT players
                    if days_from_today.days < 3 and not simulation_mode:
                        roster_df = roster_df[roster_df.status != 'O']
                    try:
                        roster_with_projections = self.player_projections.loc[
                                                  roster_df.index.intersection(self.player_projections.index), :]
                    except TypeError as e:
                        self.log.exception(e)
                if roster_change_set is not None:
                    roster_changes = roster_change_set.get(single_date)
                    if roster_changes is not None and len(roster_changes) > 0:
                        for row in roster_changes:
                            roster_with_projections = roster_with_projections.append(
                                self.player_projections.loc[row['player_in'], :])
                            roster_with_projections.loc[row['player_in'], 'GamesInLineup'] = 0
                            try:
                                roster_with_projections.drop(row['player_out'], inplace=True)
                            except KeyError as e:
                                self.log.exception(e)
                # let's double check for players on my roster who don't have current projections.  We will create our own by using this season's stats
                ids_no_stats = list(
                    roster_with_projections.query('G != G & position_type == "P" & status != "IR" ').index.values)
                if len(ids_no_stats) > 0:
                    not_cached = [i for i in ids_no_stats if i not in self.cached_player_stats]
                    if len(not_cached):
                        self.log.debug("loading {} player's info because projections missing({})".format(len(not_cached),not_cached))
                        the_stats = self.league.player_stats(not_cached, 'season')
                        for player_w_stats in the_stats:
                            self.cached_player_stats[ player_w_stats['player_id']] = player_w_stats

                    for player_id in ids_no_stats:
                        player_w_stats = self.cached_player_stats[ player_w_stats['player_id']]
                        for stat in self.tracked_stats:
                            try:
                                if player_w_stats['GP']  != '-' and player_w_stats['GP'] > 0:
                                    self.player_projections.loc[player_w_stats['player_id'], stat] = player_w_stats[
                                                                                                                   stat] / \
                                                                                                               player_w_stats[
                                                                                                                   'GP']
                                    roster_with_projections.loc[player_w_stats['player_id'], stat] = player_w_stats[
                                                                                                               stat] / \
                                                                                                           player_w_stats[
                                                                                                               'GP']
                            except TypeError as e:
                                self.log.exception("No actual stats available for: {}".format(player_w_stats))
                                break

                todays_projections = roster_with_projections.loc[:,['team_id','eligible_positions'] + self.tracked_stats].copy()
                # compute expected output for all players on roster, maximize score
                if single_date.strftime("%Y-%m-%d") not in BestRankedPlayerScorer.nhl_schedule:
                    BestRankedPlayerScorer.nhl_schedule[
                        single_date.strftime("%Y-%m-%d")] = self.nhl_scraper.games_count(
                        single_date.to_pydatetime().date(), single_date.to_pydatetime().date())

                todays_projections["GAMEPLAYED"] = todays_projections["team_id"].map(
                    BestRankedPlayerScorer.nhl_schedule[single_date.strftime("%Y-%m-%d")])
                todays_projections = todays_projections[todays_projections.GAMEPLAYED == 1]
                if len(todays_projections) > 0:
                    # goalies are trickier.  let's check rotowire to see if they are expected to play
                    # try:
                    #     todays_goalies = self.starting_goalies_df[self.starting_goalies_df['date'] == single_date]
                    #     todays_projections = todays_projections.merge(todays_goalies[['starting_status']], left_index=True,
                    #                                                   right_on='name',
                    #                                                   how='left')
                    #     todays_projections = todays_projections[(todays_projections['position_type'] != 'G') | (
                    #             (todays_projections['starting_status'] == 'Confirmed') | (
                    #             todays_projections['starting_status'] == 'Expected'))]
                    #     # todays_projections.rename(columns = {'goalie_name':'name'}, inplace = True)
                    #     todays_projections.reset_index(drop=True, inplace=True)
                    # except KeyError:
                    #     pass
                    # try:
                    #     # let's check to see if G is nan, if so, load season stats for those players from yahoo
                    #     # for a backup projection
                    #     todays_projections[
                    #         'fpts'] = todays_projections.G * stats_weights[0] + todays_projections.A * stats_weights[1] + \
                    #                   todays_projections['+/-'] * stats_weights[2] + todays_projections.PIM * stats_weights[
                    #                       3] + todays_projections.SOG * stats_weights[4] + todays_projections.FW * \
                    #                   stats_weights[5] + todays_projections.HIT * stats_weights[6]
                    # except AttributeError as e:
                    #     print(e)
                    # todays_projections = todays_projections.sort_values(by=['fpts'], ascending=False)
                    # self.log.debug("Daily roster:\n %s", todays_projections.head(20))
                    best_roster = self.roster_builder.find_best(todays_projections)
                    if best_roster is not None and len(best_roster) > 0:
                        daily_scoring_results = todays_projections.loc[best_roster.values.astype(int).tolist(), self.tracked_stats]
                        daily_scoring_results.loc[:, 'score_type'] = 'p'
                        #swap values, index so we can set roster position for players
                        swapped_roster = pd.Series([p.split('.')[0] for p in best_roster.index.values], index=best_roster )
                        daily_scoring_results['selected_position'] = swapped_roster

            if daily_scoring_results is not None and len(daily_scoring_results) > 0:
                daily_scoring_results.loc[:,'play_date'] = single_date.date()
                if projected_week_results is None:
                    projected_week_results = daily_scoring_results
                else:
                    projected_week_results = projected_week_results.append(daily_scoring_results)
        return projected_week_results

