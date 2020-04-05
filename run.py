from csh_fantasy_bot import factory
import csh_fantasy_bot

if __name__ == "__main__":
    app = factory.create_app(celery=csh_fantasy_bot.celery)
    app.run()