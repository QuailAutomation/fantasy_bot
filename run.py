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

@app.route('/run_ga/<string:week>')
def run_ga(week):
    from csh_fantasy_bot.tasks import run_ga
    run_ga.delay(week)
    return 'Sucessfully started GA.'

@app.route('/cube/<int:num>')
def cube(num):
    from csh_fantasy_bot.tasks import cube
    result = cube.delay(num)

    return str(result.get())

if __name__ == "__main__":
    if len(sys.argv) < 2 or 'ipython' != sys.argv[1]:
        try:
            app.run()
        except SystemExit as e:
            print(f"System exitted: {e}")