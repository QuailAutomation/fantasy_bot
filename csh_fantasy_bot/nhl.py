import pandas as pd
import numpy as np
import logging
from nhl_scraper.nhl import Scraper
from yahoo_fantasy_api import League, Team

player_stats = ["G", "A", "+/-", "PIM", "SOG", "FOW", "HIT"]
stats_weights = [2, 1.75, .5, .5, .5, .1, .5]
roster_makeup = "C,C,LW,LW,RW,RW,D,D,D,D".split(",")


class Scorer:
    """Class that scores rosters that it is given"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.use_weekly_sched = cfg['Scorer'].getboolean('useWeeklySchedule')

    def summarize(self, df):
        """Summarize the dataframe into individual stat categories


        :param df: Roster predictions to summarize
        :type df: DataFrame
        :return: Summarized predictions
        :rtype: Series
        """
        temp_stat_cols = ['GA', 'SV']
        stat_cols = ['G', 'A', 'SOG', 'PPP', 'PIM', 'W'] + temp_stat_cols

        res = dict.fromkeys(stat_cols, 0)
        for plyr in df.iterrows():
            p = plyr[1]
            for stat in stat_cols:
                if not np.isnan(p[stat]):
                    if self.use_weekly_sched:
                        res[stat] += p[stat] / 82 * p['WK_G']
                    else:
                        res[stat] += p[stat]

        # Handle ratio stats
        if res['SV'] > 0:
            res['SV%'] = res['SV'] / (res['SV'] + res['GA'])
        else:
            res['SV%'] = None

        # Drop the temporary values used to calculate the ratio stats
        for stat in temp_stat_cols:
            del res[stat]

        return res

    def is_counting_stat(self, stat):
        return stat not in ['SV%']

    def is_highest_better(self, stat):
        return True


class BestRankedPlayerScorer:
    nhl_schedule = {}

    def __init__(self, team_roster, player_projections, date_range, access_fa=False):
        self.logger = logging.getLogger()
        self.team_roster = team_roster
        self.player_projections = player_projections
        self.nhl_scraper: Scraper = Scraper()
        self.date_range = date_range
        self.roster_builder = Roster()
        pass

    def score(self, roster_change_set=None, results_printer=None):
        roster_df = self.team_roster

        try:
            roster_with_projections = self.player_projections[self.player_projections['name'].isin(roster_df['name'])]
        except TypeError as e:
            print(e)
        # roster_with_projections.set_index('player_id', inplace=True)
        roster_with_projections['GamesInLineup'] = int(0)
        projected_week_results = None
        for single_date in self.date_range:
            self.logger.debug("Date: %s", single_date)
            if roster_change_set is not None:
                for roster_change in roster_change_set:
                    if roster_change.change_date == single_date:
                        roster_with_projections = roster_with_projections.append(
                            self.player_projections[self.player_projections.player_id == roster_change.player_in])
                        roster_with_projections.loc[
                        roster_with_projections['player_id'].isin([roster_change.player_in]), 'GamesInLineup'] = 0
                        roster_with_projections = roster_with_projections[
                            roster_with_projections.player_id != roster_change.player_out]

            todays_projections = roster_with_projections.copy()
            # compute expected output for all players on roster, maximize score
            if single_date.strftime("%Y-%m-%d") not in BestRankedPlayerScorer.nhl_schedule:
                BestRankedPlayerScorer.nhl_schedule[single_date.strftime("%Y-%m-%d")] = self.nhl_scraper.games_count(
                    single_date, single_date)

            todays_projections["GAMEPLAYED"] = todays_projections["team_id"].map(
                BestRankedPlayerScorer.nhl_schedule[single_date.strftime("%Y-%m-%d")])
            todays_projections = todays_projections[todays_projections.GAMEPLAYED == 1]
            # "G", "A", "PLUSMINUS", "PIM", "SOG", "FOW", "HIT"]
            try:
                todays_projections[
                    'fpts'] = todays_projections.G * stats_weights[0] + todays_projections.A * stats_weights[1]+ todays_projections['+/-'] * stats_weights[2]+ todays_projections.PIM * stats_weights[3]+ todays_projections.SOG * stats_weights[4]+ todays_projections.FOW * stats_weights[5]+ todays_projections.HIT * stats_weights[6]
            except AttributeError as e:
                print(e)
            todays_projections = todays_projections.sort_values(by=['fpts'], ascending=False)
            self.logger.debug("Daily roster:\n %s", todays_projections.head(20))

            roster_results, the_roster = self.roster_builder.daily_results(todays_projections)

            roster_player_id_list = []
            for pos in the_roster.values():
                for player in pos['players']:
                    roster_player_id_list.append(player['player_id'])

            roster_with_projections.loc[roster_with_projections['player_id'].isin(roster_player_id_list), 'GamesInLineup'] += 1
            # roster_with_projections['player_id'] += roster_with_projections['GAMEPLAYED']

            self.logger.debug("roster:\n %s", roster_with_projections.head(20))
            if projected_week_results is None:
                projected_week_results = roster_results
            else:
                projected_week_results = projected_week_results.append(roster_results, ignore_index=True)

        return projected_week_results

    def _score_day(self, day):
        pass

    # fill roster, by using highest rated players as rated by fantasysp for the week.
    def _select_roster(self, game_date):

        return pd.DataFrame()


class Roster:
    def __init__(self):
        self.logger = logging.getLogger()
        self.roster = {'C': {'num': 2, 'players': []},
                       'LW': {'num': 2, 'players': []},
                       'RW': {'num': 2, 'players': []},
                       'D': {'num': 4, 'players': []}}

    def _clear_roster(self):
        self.roster = {'C': {'num': 2, 'players': []},
                       'LW': {'num': 2, 'players': []},
                       'RW': {'num': 2, 'players': []},
                       'D': {'num': 4, 'players': []}}

    # using roster makeup, maximize points
    def _add(self, position, player):
        # print('Adding to position: {}:{}'.format(position, player['name_x']))
        self.roster[position]['players'].append(player)

    def _can_accept(self, player):
        for position in player['eligible_positions']:
            if position not in ['G', 'IR']:
                try:
                    if len(self.roster[position]['players']) < self.roster[position]['num']:
                        return position
                except TypeError:
                    pass
        return False

    def _place(self, row):
        for posn in row['eligible_positions']:
            if self._is_room_as(posn):
                self.roster[posn]['players'].append(row)
                return
            else:
                if self._free_position(posn):
                    self.roster[posn]['players'].append(row)
        # did not find room, lets see if we can make space

    def _make_room(self, position):
        for player in self.roster[position]['players']:
            # can we move this player
            for position in player['eligible_positions']:
                if position != position:
                    # we have an alternative position
                    if self._is_room_as(position):
                        print('can move to: {}'.format(position))
                        return True
                    else:
                        print("can't move to: {}".format(position))
        return False

    def _is_room_as(self, position):
        if len(self.roster[position]['players']) < self.roster[position]['num']:
            return True
        else:
            return False

    def _free_position(self, position):
        return False

    def daily_results(self, projected_results):

        self._clear_roster()

        for index in projected_results.index:
            row = projected_results.loc[index]
            # print("Processing idx: {}, name: {}".format(index,row['name_x']))
            try:
                if row.fpts > 0:
                    position = self._can_accept(row)
                    if position is not False:
                        self._add(position, row)
                    else:
                        # print("rejected: {}, eligble positions: {}".format(row['name'], row['eligible_positions']))
                        pass
            except ValueError as e:
                print(e)
        results = dict.fromkeys(player_stats, 0)
        for key in self.roster:
            # print("Position: {}".format(key))
            for player in self.roster[key]['players']:
                for idx, stat_code in enumerate(player_stats):
                    results[stat_code] += player[player_stats[idx]]

        return pd.DataFrame([results], columns=player_stats), self.roster

    def _print_roster(self):
        pass