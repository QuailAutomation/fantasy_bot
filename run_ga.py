import logging
import pandas as pd
from csh_fantasy_bot import automation
import cProfile

logging.basicConfig(level=logging.INFO)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)


def do_cprofile(func):
    def profiled_func(*args, **kwargs):
        profile = cProfile.Profile()
        try:
            profile.enable()
            result = func(*args, **kwargs)
            profile.disable()
            return result
        finally:
            profile.print_stats()
    return profiled_func



@do_cprofile
def do_run():
    driver = automation.Driver()
    driver.run()

do_run()