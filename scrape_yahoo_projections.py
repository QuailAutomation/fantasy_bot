# """Load the yahoo projections for players."""
# from csh_fantasy_bot import yahoo_scraping

# scraper = yahoo_scraping.ProjectionScraper()
# scraper.scrape(pick_goalies=False,num_pages=4)

# print('Done')



from csh_fantasy_bot.yahoo_scraping import YahooPredictions, PredictionType

league_id = "411.l.85094"

y_projections = YahooPredictions(league_id, predition_type=PredictionType.rest_season)
y_projections.all_players

