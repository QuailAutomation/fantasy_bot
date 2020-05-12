"""Set up celery worker."""
import logging

from celery import Celery
from celery.signals import after_setup_logger

from csh_fantasy_bot.app import init_celery
from csh_fantasy_bot.config import LOG_LEVEL

log = logging.getLogger()

app = init_celery()
log.debug("Celery initialized")

@after_setup_logger.connect
def setup_loggers(logger, *args, **kwargs):
    """Add graylog handler to logger."""
    try:
        import graypy
        from csh_fantasy_bot.config import GELF_URL
        log.info(f'Gelf url: {GELF_URL}')
        if GELF_URL:
            handler = graypy.GELFUDPHandler(GELF_URL, 12201,
                                            facility='fantasy_bot_worker')
            logger.addHandler(handler)
    except ImportError:
        log.warn("Could not import graypy, using default logging")
    except KeyError:
        log.warn("Could not find gelf url, using default logging")
    finally:
        for k,v in  logging.Logger.manager.loggerDict.items()  :
            print('+ [%s] {%s} ' % (str.ljust( k, 20)  , str(v.__class__)[8:-2]) ) 
            if not isinstance(v, logging.PlaceHolder):
                for h in v.handlers:
                    print('     +++',str(h.__class__)[8:-2] )

log.setLevel(level=LOG_LEVEL)

if __name__ == "__main__":
    print("main of celery app")
    
