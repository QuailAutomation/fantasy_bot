import os
from pathlib import Path
import configparser

# load swarm secrets
def get_secret(secret_name, if_none=None):
    try:
        with open('/run/secrets/{0}'.format(secret_name), 'r') as secret_file:
            return secret_file.read().rstrip()
    except IOError:
        return if_none

def get_yahoo_credential(property, missing_val=None):
    config = configparser.ConfigParser()
    config.read(f'{Path.home()}/.yahoo/credentials')
    return config['main'][property]


#will load from /run/secrets/secret_name if exists
# otherwise look for ~/.yahoo/credentials (ini file), and load from there
# expecting ini file to have header [main]

# for local dev, should load credentials from ~/.yahoo/credentials
# YAHOO_LEAGUEID="41177"
# YAHOO_LEAGUEID="18782"


YAHOO_USERNAME=get_secret("YAHOO_USERNAME", get_yahoo_credential("YAHOO_USERNAME"))
YAHOO_PASSWORD=get_secret("YAHOO_PASSWORD", get_yahoo_credential("YAHOO_PASSWORD"))



