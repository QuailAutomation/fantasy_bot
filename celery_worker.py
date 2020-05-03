"""Run from ipython."""
from csh_fantasy_bot.app import init_celery
from csh_fantasy_bot.tasks import *

if __name__ == "__main__":
    init_celery()

