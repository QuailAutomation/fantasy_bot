import os

def get_docker_secret(secret_name, if_none=None):
    try:
        with open('/run/secrets/{0}'.format(secret_name), 'r') as secret_file:
            return secret_file.read().rstrip()
    except IOError:
        return if_none