

from csh_fantasy_bot.celery_app import app
# r = app.send_task('hello_world',('Craig',),queue='boxscores' )

r = app.send_task('download_boxscores',('2022-11-12',2), queue='boxscores' )
print(r.get())