"""Run flask."""
import os 

from csh_fantasy_bot import app
from csh_fantasy_bot.tasks import refresh, make_file

app = app.create_app()

@app.route('/')
def hello_world():
    refresh.delay()
    return 'Hello world!'

@app.route("/<string:fname>/<string:content>")
def makefile(fname, content):
    fpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
    make_file.delay(fpath, content)
    return f"Find your file @ <code>{fpath}</code>"


if __name__ == "__main__":
    app.run()