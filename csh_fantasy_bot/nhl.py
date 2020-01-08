import datetime
import pandas as pd
import numpy as np
import logging
from nhl_scraper.nhl import Scraper
from nhl_scraper.rotowire import Scraper as RWScraper
from yahoo_fantasy_api import League, Team

player_stats = ["G", "A", "+/-", "PIM", "SOG", "FW", "HIT"]
stats_weights = [2, 1.75, .5, .5, .5, .3, .5]
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

    def __init__(self, league, team, player_projections, date_range, access_fa=False):
        self.logger = logging.getLogger()
        self.league = league
        self.team = team
        self.team_roster = pd.DataFrame(self.team.roster())
        self.player_projections = player_projections
        self.nhl_scraper: Scraper = Scraper()
        self.date_range = date_range
        self.roster_builder = Roster()
        self.cached_actual_results = {}
        self.starting_goalies_df = RWScraper().starting_goalies()
        self.excel_writer = None

    def register_excel_writer(self,writer):
        self.excel_writer = writer

    def score(self, roster_change_set=None, results_printer=None):
        roster_df = self.team_roster
        today = datetime.date.today()
        try:
            roster_with_projections = self.player_projections[self.player_projections['name'].isin(roster_df['name'])]
            # roster_with_projections.set_index('name', inplace=True)
            # roster_with_projections.sort_index(inplace=True)
        except TypeError as e:
            print(e)
        roster_with_projections['GamesInLineup'] = int(0)
        projected_week_results = None
        for single_date in self.date_range:
            # self.logger.debug("Date: %s", single_date)
            # TODO should store change sets in dict based on day, should be faster for lookup
            if roster_change_set is not None:
                for roster_change in roster_change_set:
                    if roster_change.change_date == single_date:
                        roster_with_projections = roster_with_projections.append(
                            self.player_projections[self.player_projections.player_id == roster_change.player_in])
                        roster_with_projections.loc[
                            roster_with_projections['player_id'].isin([roster_change.player_in]), 'GamesInLineup'] = 0
                        roster_with_projections = roster_with_projections[
                            roster_with_projections.player_id != roster_change.player_out]

            roster_results = None
            the_roster = None
            roster_player_id_list = []
            if single_date < today:
                if single_date not in self.cached_actual_results:
                    # retrieve actual results as in past
                    pass
                    the_roster = self.team.roster(day=single_date)
                    opp_daily_roster = pd.DataFrame(the_roster)
                    lineup = opp_daily_roster.query('selected_position != "BN" & selected_position != "G"')
                    stats = self.league.player_stats(lineup.player_id.tolist(), "date", date=single_date)
                    daily_stats = pd.DataFrame(stats)
                    # TODO would be ideal to drop non stat tracked stats, though must keep player id, team, etc
                    # maybe this should be done over in compare, only compare stats we care about in league
                    daily_stats.drop(columns=['GP','PTS','PPG','PPA','PPP','GWG','GP','position_type','name'], inplace=True)
                    daily_stats.replace('-', np.nan,inplace=True)
                    # daily_stats.rename(columns={'FW': 'FOW'}, inplace=True)
                    self.cached_actual_results[single_date] = daily_stats[~daily_stats.G.isnull()]
                roster_results = self.cached_actual_results[single_date]
                roster_player_id_list = self.cached_actual_results[single_date].player_id.tolist()
            else:
                todays_projections = roster_with_projections.copy()
                # compute expected output for all players on roster, maximize score
                if single_date.strftime("%Y-%m-%d") not in BestRankedPlayerScorer.nhl_schedule:
                    BestRankedPlayerScorer.nhl_schedule[
                        single_date.strftime("%Y-%m-%d")] = self.nhl_scraper.games_count(
                        single_date, single_date)

                todays_projections["GAMEPLAYED"] = todays_projections["team_id"].map(
                    BestRankedPlayerScorer.nhl_schedule[single_date.strftime("%Y-%m-%d")])
                todays_projections = todays_projections[todays_projections.GAMEPLAYED == 1]
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
                try:
                    # let's check to see if G is nan, if so, load season stats for those players from yahoo
                    # for a backup projection
                    todays_projections[
                        'fpts'] = todays_projections.G * stats_weights[0] + todays_projections.A * stats_weights[1] + \
                                  todays_projections['+/-'] * stats_weights[2] + todays_projections.PIM * stats_weights[
                                      3] + todays_projections.SOG * stats_weights[4] + todays_projections.FW * \
                                  stats_weights[5] + todays_projections.HIT * stats_weights[6]
                except AttributeError as e:
                    print(e)
                todays_projections = todays_projections.sort_values(by=['fpts'], ascending=False)
                self.logger.debug("Daily roster:\n %s", todays_projections.head(20))

                roster_results, the_roster = self.roster_builder.daily_results(todays_projections)

            if len(roster_results) > 0:
                # if self.excel_writer is not None:
                #     roster_results.to_excel(self.excel_writer, single_date.strftime("%Y-%m-%d"))
                roster_with_projections.loc[
                    roster_with_projections['player_id'].isin(roster_results['player_id'].tolist()), 'GamesInLineup'] += 1

                # self.logger.debug("roster:\n %s", roster_with_projections.head(20))
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
                       'D': {'num': 4, 'players': []},
                       'G': {'num': 2, 'players': []}}

    def _clear_roster(self):
        self.roster = {'C': {'num': 2, 'players': []},
                       'LW': {'num': 2, 'players': []},
                       'RW': {'num': 2, 'players': []},
                       'D': {'num': 4, 'players': []},
                       'G': {'num': 2, 'players': []}}

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
        roster = self.roster
        day_roster  = []
        for key in roster.keys():
            for player in roster[key]['players']:
                player['position'] = key
                day_roster.append(player)

        day_df = pd.DataFrame(day_roster)
        # day_df.reset_index()
        # for key in self.roster:
        #     # print("Position: {}".format(key))
        #     for player in self.roster[key]['players']:
        #         for idx, stat_code in enumerate(player_stats):
        #             results[stat_code] += player[player_stats[idx]]
        if len(day_df) > 0:
            return day_df[player_stats + ['name','player_id','position']], self.roster
        else:
            return pd.DataFrame(), self.roster

    def _print_roster(self):
        pass
