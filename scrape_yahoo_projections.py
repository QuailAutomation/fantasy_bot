"""Load the yahoo projections for players."""
from csh_fantasy_bot import yahoo_scraping

scraper = yahoo_scraping.ProjectionScraper()
scraper.scrape(pick_goalies=False,num_pages=4)

print('Done')