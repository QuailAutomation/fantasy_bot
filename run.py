"""Run flask."""
import os 
import sys
from csh_fantasy_bot import app
from flask import request
import datetime


app = app.create_app()

@app.route('/')
def hello_world():
    # from csh_fantasy_bot.tasks import refresh
    # refresh.delay()
    return 'Hello world!'

@app.route('/load_draft')
def load_draft():
    from csh_fantasy_bot.tasks import load_draft
    load_draft.delay("403.l.41177")
    return 'Sucessfully loaded into elastic search.'

@app.route("/<string:fname>/<string:content>")
def makefile(fname, content):
    from csh_fantasy_bot.tasks import make_file
    fpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
    make_file.delay(fpath, content)
    return f"Find your file @ <code>{fpath}</code>"

@app.route('/load_predictions') # /<string:league>/<string:week>
def load_predictions(league=None, week=None): # league=None, week=None
    from csh_fantasy_bot.tasks import export_teams_results
    # from csh_fantasy_bot.tasks import make_file
    # fpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
    # make_file.delay(fpath, content)
    league = request.args.get('league')
    week = request.args.get('week')

    export_teams_results.delay(league)
    return f"load predictions into ES for league: {league}, week: {week}"

@app.route('/run_ga/<string:week>')
def run_ga(week):
    from csh_fantasy_bot.tasks import run_ga
    run_ga.delay(week)
    return 'Sucessfully started GA.'

@app.route('/check_rosters')
def check_rosters():
    # TODO add support for days from now, and specifying a date
    from csh_fantasy_bot.tasks import check_daily_roster
    result = check_daily_roster.delay()
    return str(result.get())

if __name__ == "__main__":
    if len(sys.argv) < 2 or 'ipython' != sys.argv[1]:
        try:
            app.run()
        except SystemExit as e:
            print(f"System exitted: {e}")