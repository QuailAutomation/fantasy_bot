from csh_fantasy_bot.app import init_celery

app = init_celery()
# app.conf.imports = app.conf.imports + ("csh_fantasy_bot:tasks",)