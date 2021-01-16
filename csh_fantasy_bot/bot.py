#!/bin/python
import logging
import pickle
import os
import math
import datetime
import pandas as pd
import numpy as np
import importlib
import copy


from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
from nhl_scraper.nhl import Scraper
from csh_fantasy_bot import roster, utils, builder,fantasysp_scrape
from csh_fantasy_bot.league import FantasyLeague
from csh_fantasy_bot.nhl import score_team
# from csh_fantasy_bot.nhl import BestRankedPlayerScorer
from csh_fantasy_bot.scoring import ScoreComparer

def produce_csh_ranking(predictions, scoring_categories, selector, ranking_column_name='fantasy_score'):
        """Create ranking by summing standard deviation of each stat, summing, then dividing by num stats."""
        f_mean = predictions.loc[selector,scoring_categories].mean()
        f_std =predictions.loc[selector,scoring_categories].std()
        f_std_performance = (predictions.loc[selector,scoring_categories] - f_mean)/f_std
        for stat in scoring_categories:
            predictions.loc[selector, stat + '_std'] = (predictions[stat] - f_mean[stat])/f_std[stat]
        predictions.loc[selector, ranking_column_name] = f_std_performance.sum(axis=1)/len(scoring_categories)
        return predictions

class ManagerBot:
    """A class that encapsulates an automated Yahoo! fantasy manager."""

    def __init__(self, week = None, simulation_mode=True, league_id="396.l.53432"):
        self.logger = logging.getLogger()
        self.simulation_mode = simulation_mode
        self.lg = FantasyLeague(league_id)
        self.stat_categories = [stat['display_name'] for stat in self.lg.stat_categories() if stat['position_type'] == 'P']
        self.stat_categories_goalies = [stat['display_name'] for stat in self.lg.stat_categories() if stat['position_type'] == 'G']
        self.tm = self.lg.to_team(self.lg.team_key())
        self.league_week = week or self.lg.current_week()
        try:
            (start_week, end_week) = self.lg.week_date_range(self.league_week)
            self.week = pd.date_range(start_week, end_week)
        except Exception:
            self.week = pd.date_range('2021-1-13', '2021-1-24')
        self.tm_cache = utils.TeamCache(self.tm.team_key)
        self.lg_cache = utils.LeagueCache(league_key=league_id)
        self.pred_bldr = None
        self.my_team_bldr = self._construct_roster_builder()
        self.ppool = None
        self.nhl_scraper = Scraper()
#        Display = self._get_display_class()
        self.display = builder.PlayerPrinter()
        self.blacklist = self._load_blacklist()
        self.lineup = None
        self.bench = []
        self.injury_reserve = []
        self.opp_sum = None
        self.opp_team_name = None
        self.opp_team_key = None

        self.init_prediction_builder()
        self.all_players = self.lg.as_of(self.week[0]).all_players()
        self.fetch_player_pool()
        self.all_player_predictions = self.produce_all_player_predictions()
        self.projected_league_scores = self.fetch_league_lineups()
        self.score_comparer: ScoreComparer = ScoreComparer(self.projected_league_scores.values(), self.stat_categories)
        # self.logger.debug("Reading Free Agents")
        # self.fetch_player_pool()
        self.logger.debug("Loading Lineups")
        self.load_lineup()
     #    self.pick_injury_reserve()
        self.logger.debug("auto pick opponent")
        self.auto_pick_opponent()
        self.roster_changes_made = self._get_num_roster_changes_made()
        self.roster_changes_allowed = 4 - self.roster_changes_made

    def _load_blacklist(self):
        fn = self.tm_cache.blacklist_cache_file()
        if os.path.exists(fn):
            with open(fn, "rb") as f:
                blacklist = pickle.load(f)
        else:
            blacklist = []
        return blacklist


    def pick_injury_reserve(self):
        """Pick the injury reserve slots"""
        self.injury_reserve = []
        ir_spots = 1
        if ir_spots == 0:
            return

        ir = []
        roster = self.fetch_cur_lineup()
        for plyr in roster:
            if plyr['status'] == 'IR':
                ir.append(plyr)
                for idx, lp in enumerate(self.lineup):
                    if lp['player_id'] == plyr['player_id']:
                        del self.lineup[idx]
                        break
                for idx, bp in enumerate(self.bench):
                    if bp['player_id'] == plyr['player_id']:
                        del self.bench[idx]
                        break

        if len(ir) <= ir_spots:
            self.injury_reserve = ir
        else:
            assert(False), "Need to implement pruning of IR"

    def move_non_available_players(self):
        """Remove any player that has a status (e.g. DTD, SUSP, etc.).

        If the player is important enough, they will be added back to the bench
        pending the ownership percentage.
        """
        roster = self._get_orig_roster()
        for plyr in roster:
            if plyr['status'].strip() != '':
                for idx, lp in enumerate(self.lineup):
                    if lp['player_id'] == plyr['player_id']:
                        self.logger.info(
                            "Moving {} out of the starting lineup because "
                            "they are not available ({})".format(
                                plyr['name'], plyr['status']))
                        del self.lineup[idx]
                        break

    def _save_blacklist(self):
        fn = self.tm_cache.blacklist_cache_file()
        with open(fn, "wb") as f:
            pickle.dump(self.blacklist, f)

    def add_to_blacklist(self, plyr_name):
        self.blacklist.append(plyr_name)
        self._save_blacklist()

    def remove_from_blacklist(self, plyr_name):
        if plyr_name not in self.blacklist:
            return False
        else:
            self.blacklist.remove(plyr_name)
            self._save_blacklist()
            return True

    def get_blacklist(self):
        return self.blacklist

    def init_prediction_builder(self):
        """Will load and return the prediction builder"""
        def loader():
            # module = self._get_prediction_module()
            # func = getattr('csh_fantasy_bot',
            #                self.cfg['Prediction']['builderClassLoader'])
            return fantasysp_scrape.Parser(scoring_categories=self.stat_categories)

        expiry = datetime.timedelta(minutes=24 * 60)
        self.pred_bldr = self.lg_cache.load_prediction_builder(expiry, loader)

    def save(self):
        self.tm_cache.refresh_lineup(self.lineup)
        self.tm_cache.refresh_bench(self.bench)
        self.lg_cache.refresh_prediction_builder(self.pred_bldr)

    def fetch_cur_lineup(self):
        """Fetch the current lineup as set in Yahoo!"""
        all_mine = self._get_orig_roster()
        pct_owned = self.lg.percent_owned([e['player_id'] for e in all_mine])
        for p, pct_own in zip(all_mine, pct_owned):
            if p['selected_position'] == 'BN' or \
                    p['selected_position'] == 'IR':
                p['selected_position'] = np.nan
            assert(pct_own['player_id'] == p['player_id'])
            p['percent_owned'] = pct_own['percent_owned']
            p['fantasy_status'] = int(self.tm.team_key.split('.')[-1])
        return all_mine

    def _get_predicted_stats(self, my_roster):

        self._fix_yahoo_team_abbr(my_roster)
        self.nhl_scraper = Scraper()

        nhl_teams = self.nhl_scraper.teams()
        nhl_teams.set_index("id")
        nhl_teams.rename(columns={'name': 'team_name'}, inplace=True)

        my_roster = my_roster.merge(nhl_teams, left_on='editorial_team_abbr', right_on='abbrev')
        my_roster.rename(columns={'id': 'team_id'}, inplace=True)
        # self.ppool.rename(columns={'Name': 'name'}, inplace=True)
        # self.nhl_players = self.nhl_scraper.players()

        players = self.pred_bldr.predict(my_roster)
        # start_week,end_week = self.lg.week_date_range(self.lg.current_week())
        # let's double check for players on my roster who don't have current projections.  We will create our own by using this season's stats
        ids_no_stats = list(
            players.query('G != G & position_type == "P" & status != "IR"').index.values)
        the_stats = self.lg.player_stats(ids_no_stats, 'season')
        
        for player_w_stats in the_stats:
            for stat in self.stat_categories:
                if player_w_stats['GP'] > 0:
                    players.loc[player_w_stats['player_id'], [stat]] = player_w_stats[
                                                                                                       stat] / \
                                                                                                   player_w_stats['GP']
        return players

    def _fix_yahoo_team_abbr(self, df):
        nhl_team_mappings = {'LA': 'LAK', 'Ott': 'OTT', 'Bos': 'BOS', 'SJ': 'SJS', 'Anh': 'ANA', 'Min': 'MIN',
                             'Nsh': 'NSH',
                             'Tor': 'TOR', 'StL': 'STL', 'Det': 'DET', 'Edm': 'EDM', 'Chi': 'CHI', 'TB': 'TBL',
                             'Fla': 'FLA',
                             'Dal': 'DAL', 'Van': 'VAN', 'NJ': 'NJD', 'Mon': 'MTL', 'Ari': 'ARI', 'Wpg': 'WPG',
                             'Pit': 'PIT',
                             'Was': 'WSH', 'Cls': 'CBJ', 'Col': 'COL', 'Car': 'CAR', 'Buf': 'BUF', 'Cgy': 'CGY',
                             'Phi': 'PHI'}
        df["editorial_team_abbr"].replace(nhl_team_mappings, inplace=True)

    def fetch_all_players(self):
        def all_loader():
            return self.lg.all_players()

        expiry = datetime.timedelta(minutes=6 * 60 * 20)
        return self.lg_cache.load_all_players(expiry,all_loader)

    def fetch_player_pool(self):
        """Build the roster pool of players."""
        if self.ppool is None:
            my_team_id = int(self.tm.team_key.split('.')[-1])
            if self.simulation_mode:
                all_players = self.all_players
                
                my_roster = all_players[all_players.fantasy_status.isin([my_team_id, 'FA'])]
                my_roster.reset_index(inplace=True)
            else:
                current_lineup = self.fetch_cur_lineup()
                plyr_pool = self.fetch_free_agents() + current_lineup + self.fetch_waivers()
                my_roster = pd.DataFrame(plyr_pool)
                self._fix_yahoo_team_abbr(my_roster)
                self.nhl_scraper = Scraper()

                nhl_teams = self.nhl_scraper.teams()
                nhl_teams.set_index("id")
                nhl_teams.rename(columns={'name': 'team_name'}, inplace=True)

                my_roster = my_roster.merge(nhl_teams, left_on='editorial_team_abbr', right_on='abbrev')
                my_roster.rename(columns={'id': 'team_id'}, inplace=True)

            players = self.pred_bldr.predict(my_roster)
            # let's double check for players on my roster who don't have current projections.  We will create our own by using this season's stats
            ids_no_stats = list(players.query(f'fantasy_status == {my_team_id} & G != G & position_type == "P" & status != "IR" ').index.values)
            the_stats = self.lg.player_stats(ids_no_stats,'season')
            
            for player_w_stats in the_stats:
                # a_player = players[players.player_id == player_w_stats['player_id']]
                for stat in self.stat_categories:
                    if player_w_stats['GP'] != '-' and player_w_stats['GP'] > 0:
                        players.loc[player_w_stats['player_id'], [stat]] = player_w_stats[stat] / player_w_stats['GP']

            self.ppool = players.query('~(G != G & position_type == "P" )')
            pass

    def fetch_waivers(self):
        def loader():
            self.logger.info("Fetching waivers")
            fa = self.lg.waivers1()
            self.logger.info(
                "Waivers fetch complete.  {} players in pool".
                format(len(fa)))
            return fa

        expiry = datetime.timedelta(minutes= 360)
        return self.lg_cache.load_waivers(expiry, loader)

    def fetch_free_agents(self):
        def loader():
            self.logger.info("Fetching free agents")
            fa = self.lg.free_agents(None)
            self.logger.info(
                "Free agents fetch complete.  {} players in pool".
                format(len(fa)))
            return fa

        expiry = datetime.timedelta(minutes= 360 * 50)
        return self.lg_cache.load_free_agents(expiry, loader)

    def produce_all_player_predictions(self):
        all_projections = self.pred_bldr.predict(self.all_players.reset_index())
       
        produce_csh_ranking(all_projections, self.stat_categories, 
                    all_projections.index, ranking_column_name='fpts')
        #TODO this can be removed with support for goalies
        return all_projections[(all_projections.position_type == 'P') & (all_projections.status != 'IR')]

    def fetch_league_lineups(self):
        scoring_results = {tm['team_key'].split('.')[-1]:self.score_team(self.all_player_predictions[self.all_player_predictions.fantasy_status == int(tm['team_key'].split('.')[-1])], \
                                    self.week, \
                                    self.stat_categories)[1] 
                                for tm in self.lg.teams()}
        return scoring_results

    def team_roster(self, team_id):
        all_projections = self.pred_bldr.predict(self.all_players.reset_index())
        projections_no_goalies = all_projections[all_projections.position_type == 'P']
        return projections_no_goalies[projections_no_goalies.fantasy_status == int(team_id.split('.')[-1])]

    def score_team(self, player_projections, date_range=None, scoring_categories=None, roster_change_set=None, simulation_mode=True):
        if date_range is None:
            date_range = self.week
        if scoring_categories is None:
            scoring_categories = self.stat_categories

        return score_team(player_projections, date_range, scoring_categories, roster_change_set, simulation_mode)


    def invalidate_free_agents(self, plyrs):
        if os.path.exists(self.lg_cache.free_agents_cache_file()):
            with open(self.lg_cache.free_agents_cache_file(), "rb") as f:
                free_agents = pickle.load(f)

            plyr_ids = [e["player_id"] for e in plyrs]
            self.logger.info("Removing player IDs from free agent cache".
                             format(plyr_ids))
            new_players = [e for e in free_agents["payload"]
                           if e['player_id'] not in plyr_ids]
            free_agents['payload'] = new_players
            with open(self.lg_cache.free_agents_cache_file(), "wb") as f:
                pickle.dump(free_agents, f)

    def sum_opponent(self, opp_team_key):
        # Build up the predicted score of the opponent
        try:
            team_name = self._get_team_name(self.lg, opp_team_key)
            print("opponent: {}".format(team_name))
        except LookupError:
            print("Not a valid team: {}:".format(opp_team_key))
            return(None, None)

        # opp_team = roster.Container(self.lg, self.lg.to_team(opp_team_key))
        # opp_roster = pd.DataFrame(self.lg.to_team(opp_team_key).roster())
        # opp_roster = self._get_predicted_stats(opp_roster)
        # # opp_df = self.pred_bldr.predict(pd.DataFrame(opp_roster))

        # print(opp_roster.head(20))
        # my_scorer: BestRankedPlayerScorer = BestRankedPlayerScorer(self.lg, self.lg.to_team(opp_team_key),self.pred_bldr.predict(
        #     players.reset_index()),
                                                                    # self.week)
        #opp_sum = self.scorer.summarize(opp_df, week)
        # opp_sum = my_scorer.score()
       # print(opp_sum.head(20))
        return (team_name, self.projected_league_scores[opp_team_key.split('.')[-1]])

    def load_lineup(self):
        def loader():
            self.lineup = []
            # self.sync_lineup()
            return self.lineup

        self.lineup = self.tm_cache.load_lineup(None, loader)

    def _set_new_lineup_and_bench(self, new_lineup):
        new_bench = []
        new_plyr_ids = [e["player_id"] for e in new_lineup]
        for plyr in self.lineup:
            if plyr["player_id"] not in new_plyr_ids:
                new_bench.append(plyr)
        for plyr in self.bench:
            if plyr["player_id"] not in new_plyr_ids:
                new_bench.append(plyr)
        assert(len(new_bench) <= 8)
        self.lineup = new_lineup
        self.bench = new_bench

    def fill_empty_spots_from_bench(self):
        if len(self.lineup) < self.my_team_bldr.max_players() and \
                len(self.bench) > 0:
            optimizer_func = self._get_lineup_optimizer_function()
            bench_df = pd.DataFrame(data=self.bench,
                                    columns=self.bench[0].index)
            new_lineup = optimizer_func(self.cfg, self.score_comparer,
                                        self.my_team_bldr, bench_df,
                                        self.lineup)
            if new_lineup:
                self._set_new_lineup_and_bench(new_lineup)

    def optimize_lineup_from_bench(self):
        """
        Optimizes your lineup using just your bench as potential player
        """
        if len(self.bench) == 0:
            return

        optimizer_func = self._get_lineup_optimizer_function()
        ppool = pd.DataFrame(data=self.bench, columns=self.bench[0].index)
        ldf = pd.DataFrame(data=self.lineup, columns=self.lineup[0].index)
        ppool = ppool.append(ldf, ignore_index=True)
        ppool = ppool[ppool['status'] == '']
        new_lineup = optimizer_func(self.score_comparer,
                                    self.my_team_bldr, ppool, [])
        if new_lineup:
            self._set_new_lineup_and_bench(new_lineup)

    def fill_empty_spots(self):
        if len(self.lineup) < self.my_team_bldr.max_players():
            optimizer_func = self._get_lineup_optimizer_function()
            new_lineup = optimizer_func(self.score_comparer,
                                        self.my_team_bldr,
                                        self._get_filtered_pool(), self.lineup)
            if new_lineup:
                self.lineup = new_lineup

    def print_roster(self):
        self.display.printRoster(self.lineup, self.bench, self.injury_reserve)

    def sync_lineup(self):
        """Reset the local lineup to the one that is set in Yahoo!"""
        yahoo_roster = self._get_orig_roster()
        roster_ids = [e['player_id'] for e in yahoo_roster]
        bench_ids = [e['player_id'] for e in yahoo_roster
                     if e['selected_position'] == 'BN']
        ir_ids = [e['player_id'] for e in yahoo_roster
                  if (e['selected_position'] == 'DL' or
                      e['selected_position'] == 'IR')]
        sel_plyrs = self.ppool.loc[roster_ids,:]
        lineup = []
        bench = []
        ir = []
        for plyr in sel_plyrs.iterrows():
            if plyr[0] in bench_ids:
                bench.append(plyr[1])
            elif plyr[0] in ir_ids:
                ir.append(plyr[1])
            else:
                lineup.append(plyr[1])
        self.lineup = lineup
        self.bench = bench
        self.injury_reserve = ir

    def _get_filtered_pool(self):
        """
        Get a list of players from the pool filtered on common crigeria

        :return: Player pool
        :rtype: DataFrame
        """
        avail_plyrs = self.ppool[~self.ppool['name'].isin(self.blacklist)]
        avail_plyrs = avail_plyrs[avail_plyrs['percent_owned'] > 5]
        return avail_plyrs[avail_plyrs['status'] == '']

    def optimize_with_pygenetic(self):
        """Utilize pygenetic to run GA."""
        

    def optimize_lineup_from_free_agents(self):
        """
        Optimize your lineup using all of your players plus free agents.
        """
        optimizer_func = self._get_lineup_optimizer_function()
        locked_plyrs = self.all_players[(self.all_players['fantasy_status'] == 2) & (self.all_players['percent_owned'] > 93) ].index.tolist()
        best_lineup = optimizer_func(self.score_comparer,
                                     self.ppool, locked_plyrs, self.lg, self.league_week, simulation_mode=True)

        if best_lineup:
            self.score_comparer.print_week_results(best_lineup.scoring_summary)


    def list_players(self, pos):
        self.display.printListPlayerHeading(pos)

        for plyr in self.ppool.iterrows():
            if pos in plyr[1]['eligible_positions']:
                self.display.printPlayer(pos, plyr)

    def find_in_lineup(self, name):
        for idx, p in enumerate(self.lineup):
            if p['name'] == name:
                return idx
        raise LookupError("Could not find player: " + name)

    def swap_player(self, plyr_name_del, plyr_name_add):
        if plyr_name_add:
            plyr_add_df = self.ppool[self.ppool['name'] == plyr_name_add]
            if(len(plyr_add_df.index) == 0):
                raise LookupError("Could not find player in pool: {}".format(
                    plyr_name_add))
            if(len(plyr_add_df.index) > 1):
                raise LookupError("Found more than one player!: {}".format(
                    plyr_name_add))
            plyr_add = plyr_add_df.iloc(0)[0]
        else:
            plyr_add = None

        idx = self.find_in_lineup(plyr_name_del)
        plyr_del = self.lineup[idx]
        assert(type(plyr_del.selected_position) == str)
        if plyr_add and plyr_del.selected_position not in \
                plyr_add['eligible_positions']:
            raise ValueError("Position {} is not a valid position for {}: {}".
                             format(plyr_del.selected_position,
                                    plyr_add['name'],
                                    plyr_add['eligible_positions']))

        if plyr_add:
            plyr_add['selected_position'] = plyr_del['selected_position']
        plyr_del['selected_position'] = np.nan
        if plyr_add:
            self.lineup[idx] = plyr_add
        else:
            del(self.lineup[idx])
        self.pick_bench()

    def apply_roster_moves(self, dry_run):
        """Make roster changes with Yahoo!

        :param dry_run: Just enumerate the roster moves but don't apply yet
        :type dry_run: bool
        """
        roster_chg = RosterChanger(self.lg, dry_run, self._get_orig_roster(),
                                   self.lineup, self.bench,
                                   self.injury_reserve)
        roster_chg.apply()

        # Change the free agent cache to remove the players we added
        if not dry_run and False:
            adds = roster_chg.get_adds_completed()
            self.invalidate_free_agents(adds)

    def pick_opponent(self, opp_team_key):
        (self.opp_team_name, self.opp_sum) = self.sum_opponent(opp_team_key)
        if self.opp_sum is not None:
            self.score_comparer.set_opponent(self.opp_sum.sum())

    def auto_pick_opponent(self):

        edit_wk = self.league_week
        print("Picking opponent for week: {}".format(edit_wk))
        # (wk_start, wk_end) = self.lg.week_date_range(edit_wk)
        # edit_date = self.lg.edit_date()
        # if edit_date > wk_end:
        #     edit_wk += 1

        try:
            self.opp_team_key = self.tm.matchup(edit_wk)
        except RuntimeError:
            self.logger.info("Could not find opponent.  Picking ourselves...")
            opp_team_key = self.lg.team_key()

        if self.opp_team_key is None:
            print('no opp found, plugging in Lee for playoffs')
            self.opp_team_key = '396.l.53432.t.4'
        self.pick_opponent(self.opp_team_key)

    def evaluate_trades(self, dry_run, verbose):
        """
        Find any proposed trades against my team and evaluate them.

        :param dry_run: True if we will evaluate the trades but not send the
            accept or reject through to Yahoo.
        :param verbose: If true, we will print details to the console
        :return: Number of trades evaluated
        """
        trades = self.tm.proposed_trades()
        self.logger.info(trades)
        # We don't evaluate trades that we sent out.
        actionable_trades = [tr for tr in trades
                             if tr['tradee_team_key'] == self.tm.team_key]
        self.logger.info(actionable_trades)

        if len(actionable_trades) > 0:
            for trade in actionable_trades:
                ev = self._evaluate_trade(trade)
                if verbose:
                    self._print_trade(trade, ev)
                self.logger.warn("Accept={}    {}".format(ev, trade))
                if not dry_run:
                    if ev:
                        self.tm.accept_trade(trade['transaction_key'])
                    else:
                        self.tm.reject_trade(trade['transaction_key'])
        return len(actionable_trades)

    def _evaluate_trade(self, trade):
        """
        Evaluate a single trade

        :return: True if trade should be accepted.  False otherwise.
        """
        if False:
            return False
        else:
            assert(False), "No support for evaluating trades"

    def _print_trade(self, trade, ev):
        print("\nSending")
        for plyr in trade['trader_players']:
            print("  {}".format(plyr['name']))
        print("for your")
        for plyr in trade['tradee_players']:
            print("  {}".format(plyr['name']))
        print("\nTrade should be {}".format("accepted" if ev else "rejected"))

    def _get_team_name(self, lg, team_key):
        for team in lg.teams():
            if team['team_key'] == team_key:
                return team['name']
        raise LookupError("Could not find team for team key: {}".format(
            team_key))

    def _get_prediction_module(self):
        """Return the module to use for the prediction builder.

        The details about what prediction builder is taken from the config.
        """
        return importlib.import_module(
            self.cfg['Prediction']['builderModule'],
            package=self.cfg['Prediction']['builderPackage'])

    def _get_scorer_class(self):
        module = importlib.import_module(
            self.cfg['Scorer']['module'],
            package=self.cfg['Scorer']['package'])
        return getattr(module, self.cfg['Scorer']['class'])

    def _get_display_class(self):
        module = importlib.import_module(
            self.cfg['Display']['module'],
            package=self.cfg['Display']['package'])
        return getattr(module, self.cfg['Display']['class'])

    def _get_lineup_optimizer_function(self):
        """Return the function used to optimize a lineup.

        The config file is used to determine the appropriate function.
        """
        module = importlib.import_module('.roster_change_optimizer',
            package='csh_fantasy_bot')
        return getattr(module, 'optimize_with_genetic_algorithm')

    def _construct_roster_builder(self):
        pos_list = "C,C,LW,LW,RW,RW,D,D,D,D".split(",")
        return roster.Builder(pos_list)

    def _get_position_types(self):
        settings = self.lg.settings()
        position_types = {'mlb': ['B', 'P'], 'nhl': ['P']}
        return position_types[settings['game_code']]

    def _get_orig_roster(self):
        if self.simulation_mode:
            return self.tm.roster(day=self.week[0])
        else:
            return self.tm.roster(day=self.lg.edit_date())

    def _get_num_roster_changes_made(self):
        # if the game week is in the future then we couldn't have already made changes
        if datetime.date.today() < self.week[0]:
            return 0

        def retrieve_attribute_from_team_info(team_info, attribute):
            for attr in team_info:
                if attribute in attr:
                    return attr[attribute]

        raw_matchups = self.lg.matchups()
        team_id = self.tm.team_key.split('.')[-1]
        num_matchups = raw_matchups['fantasy_content']['league'][1]['scoreboard']['0']['matchups']['count']
        for matchup_index in range(0, num_matchups):
            matchup = raw_matchups['fantasy_content']['league'][1]['scoreboard']['0']['matchups'][str(matchup_index)]
            for i in range(0, 2):
                try:
                    if retrieve_attribute_from_team_info(matchup['matchup']['0']['teams'][str(i)]['team'][0],
                                                         'team_id') == team_id:
                        return int(
                            retrieve_attribute_from_team_info(matchup['matchup']['0']['teams'][str(i)]['team'][0],
                                                              'roster_adds')['value'])
                except TypeError as e:
                    pass
        #TODO should check if playoffs
        plug_value = 0
        print("returning {} for roster changes, as no matchup found".format(plug_value))
        return plug_value
        assert False, 'Did not find roster changes for team'

class RosterChanger:
    def __init__(self, lg, dry_run, orig_roster, lineup, bench,
                 injury_reserve):
        self.lg = lg
        self.tm = lg.to_team(lg.team_key())
        self.dry_run = dry_run
        self.orig_roster = orig_roster
        self.lineup = lineup
        self.bench = bench
        self.injury_reserve = injury_reserve
        self.orig_roster_ids = [e['player_id'] for e in orig_roster]
        self.new_roster_ids = [e['player_id'] for e in lineup] + \
            [e['player_id'] for e in bench] + \
            [e['player_id'] for e in injury_reserve]
        self.adds = []
        self.drops = []
        self.adds_completed = []

    def apply(self):
        self._calc_player_drops()
        self._calc_player_adds()
        # Need to drop players first in case the person on IR isn't dropped
        self._apply_player_drops()
        self._apply_ir_moves()
        self._apply_player_adds_and_drops()
        self._apply_position_selector()

    def get_adds_completed(self):
        return self.adds_completed

    def _calc_player_drops(self):
        self.drops = []
        for plyr in self.orig_roster:
            if plyr['player_id'] not in self.new_roster_ids:
                self.drops.append(plyr)

    def _calc_player_adds(self):
        self.adds = []
        for plyr in self.lineup + self.bench:
            if plyr['player_id'] not in self.orig_roster_ids:
                self.adds.append(plyr)

    def _apply_player_drops(self):
        while len(self.drops) > len(self.adds):
            plyr = self.drops.pop()
            print("Drop " + plyr['name'])
            if not self.dry_run:
                self.tm.drop_player(plyr['player_id'])

    def _apply_player_adds_and_drops(self):
        while len(self.drops) != len(self.adds):
            if len(self.drops) > len(self.adds):
                plyr = self.drops.pop()
                print("Drop " + plyr['name'])
                if not self.dry_run:
                    self.tm.drop_player(plyr['player_id'])
            else:
                plyr = self.adds.pop()
                self.adds_completed.append(plyr)
                print("Add " + plyr['name'])
                if not self.dry_run:
                    self.tm.add_player(plyr['player_id'])

        for add_plyr, drop_plyr in zip(self.adds, self.drops):
            self.adds_completed.append(add_plyr)
            print("Add {} and drop {}".format(add_plyr['name'],
                                              drop_plyr['name']))
            if not self.dry_run:
                self.tm.add_and_drop_players(add_plyr['player_id'],
                                             drop_plyr['player_id'])

    def _apply_one_player_drop(self):
        if len(self.drops) > 0:
            plyr = self.drops.pop()
            print("Drop " + plyr['name'])
            if not self.dry_run:
                self.tm.drop_player(plyr['player_id'])

    def _apply_ir_moves(self):
        orig_ir = [e for e in self.orig_roster
                   if e['selected_position'] == 'IR']
        new_ir_ids = [e['player_id'] for e in self.injury_reserve]
        pos_change = []
        num_drops = 0
        for plyr in orig_ir:
            if plyr['player_id'] in self.new_roster_ids and \
                    plyr['player_id'] not in new_ir_ids:
                pos_change.append({'player_id': plyr['player_id'],
                                   'selected_position': 'BN',
                                   'name': plyr['name']})
                num_drops += 1

        for plyr in self.injury_reserve:
            assert(plyr['player_id'] in self.orig_roster_ids)
            pos_change.append({'player_id': plyr['player_id'],
                               'selected_position': 'IR',
                               'name': plyr['name']})
            num_drops -= 1

        # Prior to changing any of the IR spots, we may need to drop players.
        # The number has been precalculated in the above loops.  Basically the
        # different in the number of players moving out of IR v.s. moving into
        # IR.
        for _ in range(num_drops):
            self._apply_one_player_drop()

        for plyr in pos_change:
            print("Move {} to {}".format(plyr['name'],
                                         plyr['selected_position']))
        if len(pos_change) > 0 and not self.dry_run:
            self.tm.change_positions(self.lg.edit_date(), pos_change)

    def _apply_position_selector(self):
        pos_change = []
        for plyr in self.lineup:
            pos_change.append({'player_id': plyr['player_id'],
                               'selected_position': plyr['selected_position']})
            print("Move {} to {}".format(plyr['name'],
                                         plyr['selected_position']))
        for plyr in self.bench:
            pos_change.append({'player_id': plyr['player_id'],
                               'selected_position': 'BN'})
            print("Move {} to BN".format(plyr['name']))

        if not self.dry_run:
            self.tm.change_positions(self.lg.edit_date(), pos_change)

