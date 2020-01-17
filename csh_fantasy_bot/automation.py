#!/bin/python

from csh_fantasy_bot import bot


class Driver(object):
    """
    Driver to do automated actions with the bot.

    :param cfg: ConfigParser read in
    """
    def __init__(self):
        self.bot = bot.ManagerBot(15)

    def run(self):
        # self.bot.sync_lineup()
      #  self.bot.evaluate_trades(dry_run=False, verbose=True)
      #   self.bot.pick_injury_reserve()
      #   self.bot.move_non_available_players()
      #   self.bot.fill_empty_spots_from_bench()
        # self.bot.fill_empty_spots()
      #  self.bot.pick_bench()
        #self.bot.optimize_lineup_from_bench()
        self.bot.optimize_lineup_from_free_agents()
    #    self.bot.apply_roster_moves(dry_run=True)
