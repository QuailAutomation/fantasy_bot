from nhl_scraper.nhl import Scraper
from datetime import datetime, timedelta

scraper = Scraper()
now = datetime.now().date()
games_today = scraper.games_count(now,now)
print(games_today)

