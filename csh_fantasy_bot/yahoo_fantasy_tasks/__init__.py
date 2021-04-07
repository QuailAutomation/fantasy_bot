
import os
import unittest.mock as mock
from yahoo_oauth import OAuth2
from csh_fantasy_bot.redis import RedisClient

from csh_fantasy_bot.config import OAUTH_TOKEN_BACKING, CacheBacking

def my_get_data(filename):
    print('works')
    return RedisClient().conn.get(filename)


@mock.patch('yahoo_oauth.oauth.get_data', side_effect=my_get_data)
def patched_load(mock):
    token =  OAuth2(None, None, from_file='./oauth2.json')
    return token



oauth_token = None
if OAUTH_TOKEN_BACKING == CacheBacking.redis:
    print("NOT IMPLEMENTED, READ auth token from redis")
    oauth_token = patched_load()

    print("token received")
else:
    oauth_file = os.getenv("YAHOO_OAUTH_FILE",default='./oauth2.json')
    oauth_token = OAuth2(None, None, from_file=oauth_file)



