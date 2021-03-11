import redis
import os


rd = redis.Redis(host="192.168.1.211")

token = None
with open("oauth2.json") as f:
    token = f.read()

rd.set("yahoo_oauth",  token)