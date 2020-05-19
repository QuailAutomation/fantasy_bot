#!/usr/bin/python

import unicodedata
import os
import logging
import pickle
import datetime


def normalized(name):
    """Normalize a name to remove any accents

    :param name: Input name to normalize
    :type name: str
    :return: Normalized name
    :rtype: str
    """
    return unicodedata.normalize('NFD', name).encode(
        'ascii', 'ignore').decode('utf-8')


class CacheBase(object):
    def __init__(self, cache_dir):
        self.logger = logging.getLogger()

        self.cache_dir = cache_dir
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def run_loader(self, fn, expiry, loader):
        cached_data = None

        if os.path.exists(fn):
            with open(fn, "rb") as f:
                cached_data = pickle.load(f)
            if type(cached_data) != dict or "expiry" not in cached_data or \
                    "payload" not in cached_data:
                cached_data = None
            elif cached_data["expiry"] is not None:
                if datetime.datetime.now() > cached_data["expiry"]:
                    self.logger.info(
                        "{} file is stale.  Expired at {}".
                        format(fn, cached_data["expiry"]))
                    cached_data = None

        if cached_data is None:
            self.logger.info("Building new {} file".format(fn))
            cached_data = {}
            cached_data["payload"] = loader()
            if expiry is not None:
                cached_data["expiry"] = datetime.datetime.now() + expiry
            else:
                cached_data["expiry"] = None
            with open(fn, "wb") as f:
                pickle.dump(cached_data, f)
            self.logger.info("Finished building {} file".format(fn))

        return cached_data["payload"]

    def refresh_cache_file(self, fn, refresh_payload):
        assert(os.path.exists(fn))
        with open(fn, "rb") as f:
            cached_data = pickle.load(f)
        assert("payload" in cached_data)
        cached_data['payload'] = refresh_payload
        with open(fn, "wb") as f:
            pickle.dump(cached_data, f)


class TeamCache(CacheBase):
    def __init__(self,  team_key):
        super(TeamCache, self).__init__(
             "{}/{}".format(".cache/", team_key))

    def lineup_cache_file(self):
        return "{}/lineup.pkl".format(self.cache_dir)

    def load_lineup(self, expiry, loader):
        return self.run_loader(self.lineup_cache_file(), expiry, loader)

    def refresh_lineup(self, lineup):
        self.refresh_cache_file(self.lineup_cache_file(), lineup)

    def bench_cache_file(self):
        return "{}/bench.pkl".format(self.cache_dir)

    def load_bench(self, expiry, loader):
        return self.run_loader(self.bench_cache_file(), expiry, loader)

    def refresh_bench(self, bench):
        self.refresh_cache_file(self.bench_cache_file(), bench)

    def blacklist_cache_file(self):
        return "{}/blacklist.pkl".format(self.cache_dir)


class LeagueCache(CacheBase):
    def __init__(self, league_key='396.l.53432'):
        super(LeagueCache, self).__init__(f".cache/{league_key}")

    def free_agents_cache_file(self):
        return "{}/free_agents.pkl".format(self.cache_dir)

    def all_players_cache_file(self):
        return "{}/all_players.pkl".format(self.cache_dir)

    def waivers_cache_file(self):
        return "{}/waivers.pkl".format(self.cache_dir)

    def load_all_players(self, expiry, loader):
        return self.run_loader(self.all_players_cache_file(), expiry, loader)

    def load_free_agents(self, expiry, loader):
        return self.run_loader(self.free_agents_cache_file(), expiry, loader)

    def load_waivers(self, expiry, loader):
        return self.run_loader(self.waivers_cache_file(), expiry, loader)

    def league_lineup_file(self):
        return "{}/lg_lineups.pkl".format(self.cache_dir)
    
    def league_transaction_file(self):
        return "{}/transactions.pkl".format(self.cache_dir)

    def load_league_lineup(self, expiry, loader):
        return self.run_loader(self.league_lineup_file(), expiry, loader)

    def load_transactions(self, expiry, loader):
        return self.run_loader(self.league_transaction_file(), expiry, loader)

    def prediction_builder_file(self):
        return "{}/pred_builder.pkl".format(self.cache_dir)

    def load_prediction_builder(self, expiry, loader):
        return self.run_loader(self.prediction_builder_file(), expiry, loader)

    def refresh_prediction_builder(self, pred_bldr):
        self.refresh_cache_file(self.prediction_builder_file(), pred_bldr)

