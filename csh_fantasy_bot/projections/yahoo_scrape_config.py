scraping_config = {"nfl": {
                    "projections": {
                            "url": 'https://football.fantasysports.yahoo.com/f1/{league_suffix}/players?status=ALL&pos={args["scrape_info"]["stat_code"]}&stat1={args["projection_length"]}&sort=AR&sdir=1&count={cnt}',
                            "scrape_config" : {"O":
                                                {
                                                    "num_pages_scrape": 1,
                                                    "stat_code": "O",
                                                    'scoring_stats':{
                                                        'name': 'td[contains(@class,"player")]/div/div/div[contains(@class,"ysf-player-name")]/a',
                                                        'position': 'td[contains(@class,"player")]/div/div/div[contains(@class,"ysf-player-name")]/span',
                                                        'player_id': 'td[contains(@class,"player")]/div/div/span/a',
                                                        'GP': 'td[6]',
                                                        'Bye': 'td[7]',
                                                        'fan_points': 'td[8]',
                                                        'overall_rank': 'td[9]',
                                                        'percent_rostered': 'td[11]',
                                                        'pass_yds': 'td[12]',
                                                        'pass_td': 'td[13]',
                                                        'pass_int': 'td[14]',
                                                        'pass_sack': 'td[15]',
                                                        'rush_attempts': 'td[16]',
                                                        'rush_yards': 'td[17]',
                                                        'rush_tds': 'td[18]',
                                                        'receiving_targets': 'td[19]',
                                                        'receiving_receptions': 'td[20]',
                                                        'receiving_yards': 'td[21]',
                                                        'receiving_tds': 'td[22]',}
                                            }
                            },
                    },
                    "draft_results": "nfl_draft_url"
                },
                "nhl": {
                    "projections": "nhl_projection_url",
                    "draft_results": "nhl_draft_url"
                }
}