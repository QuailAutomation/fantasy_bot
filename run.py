"""Run flask."""
import os 
import sys
from csh_fantasy_bot import app


app = app.create_app()

@app.route('/')
def hello_world():
    from csh_fantasy_bot.tasks import refresh
    refresh.delay()
    return 'Hello world!'

@app.route('/load_draft')
def load_draft():
    from csh_fantasy_bot.tasks import load_draft
    load_draft.delay("396.l.53432")
    return 'Sucessfully loaded into elastic search.'

@app.route("/<string:fname>/<string:content>")
def makefile(fname, content):
    from csh_fantasy_bot.tasks import make_file
    fpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
    make_file.delay(fpath, content)
    return f"Find your file @ <code>{fpath}</code>"


if __name__ == "__main__":
    if 'ipython' != sys.argv[1]:
        try:
            app.run()
        except SystemExit as e:
            print(f"System exitted: {e}")