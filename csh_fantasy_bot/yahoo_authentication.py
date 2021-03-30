import unittest.mock as mock
import json
import os

from yahoo_oauth import OAuth2

from csh_fantasy_bot import RedisClient
from csh_fantasy_bot.config import OAUTH_TOKEN_BACKING, CacheBacking
import logging

logger = logging.getLogger(__name__)

def my_get_data(filename):
    logger.debug(f"Retrieving token using key {filename} from redis")
    return json.loads(RedisClient().conn.get(filename))

def my_write_data(data, filename):
    RedisClient().conn.set(filename, json.dumps(data, indent=4, sort_keys=True, ensure_ascii=False))

@mock.patch('yahoo_oauth.oauth.get_data', side_effect=my_get_data)
@mock.patch('yahoo_oauth.oauth.write_data', side_effect=my_write_data)
def new_main(mock1, mock2):
    oauth = OAuth2(None, None, from_file='yahoo_oauth')
    return oauth
    # .....

if OAUTH_TOKEN_BACKING == CacheBacking.redis:
    oauth_token = new_main()
else:
    oauth_file = os.getenv("YAHOO_OAUTH_FILE",default='./oauth2.json')
    oauth_token = OAuth2(None, None, from_file=oauth_file)
