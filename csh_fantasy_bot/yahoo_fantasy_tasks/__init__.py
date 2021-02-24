from csh_fantasy_bot import RedisClient
import os

import redis

from yahoo_oauth import OAuth2
from csh_fantasy_bot.config import OAUTH_TOKEN_BACKING,CacheBacking

oauth_token = None
# TODO configure to read from redis
if OAUTH_TOKEN_BACKING == CacheBacking.redis.value:
    print("NOT IMPLEMENTED, READ auth token from redis")
    oauth_token = RedisClient().conn.get('yahoo_oauth')
    print("token received")
else:
    oauth_file = os.getenv("YAHOO_OAUTH_FILE",default='./oauth2.json')
    oauth_token = OAuth2(None, None, from_file=oauth_file)



