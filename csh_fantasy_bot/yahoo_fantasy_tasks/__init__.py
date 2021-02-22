import os
from yahoo_oauth import OAuth2
from csh_fantasy_bot.config import OAUTH_TOKEN_BACKING,OAuthBacking

oauth_token = None
# TODO configure to read from redis
if OAUTH_TOKEN_BACKING == OAuthBacking.redis:
    print("NOT IMPLEMENTED, READ auth token from redis")
else:
    oauth_file = os.getenv("YAHOO_OAUTH_FILE",default='./oauth2.json')
    oauth_token = OAuth2(None, None, from_file=oauth_file)