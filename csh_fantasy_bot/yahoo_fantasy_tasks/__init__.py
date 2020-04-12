import os
from yahoo_oauth import OAuth2

oauth_file = os.getenv("YAHOO_OAUTH_FILE",default='./oauth2.json')
oauth_token = OAuth2(None, None, from_file=oauth_file)