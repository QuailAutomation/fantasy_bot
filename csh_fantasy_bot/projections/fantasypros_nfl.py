# from web_scrape import remote_scrape
from csh_fantasy_bot.projections.web_scrape import remote_scrape
# https://www.fantasypros.com/nfl/rankings/half-point-ppr-cheatsheets.php
nfl_positions = ['QB', 'RB', 'WR', 'TE', 'K', 'D']
#TODO handle types of scroring (STD, ppr, 1/2 ppr)

def scrape_fp_projections(driver):
    projections = []
    url = "https://www.fantasypros.com/nfl/rankings/half-point-ppr-cheatsheets.php"
    
    page = driver.get(url)

    row_xpath = '//*[@id="ranking-table"]/tbody/tr[@class="player-row"]'
    rows = driver.find_elements_by_xpath(row_xpath)
    num_rows_processed = 0
    for row in rows:
        if num_rows_processed < 300:
            row_data = row.find_elements_by_xpath('./td')
            rank = int(row_data[0].text)
            name = row_data[2].find_element_by_xpath('.//a').text
            team = row_data[2].find_element_by_xpath('.//span[@class="player-cell-team"]').text.strip("()")
            position_rank = row_data[3].text
            projections.append({'rank': rank, 'name':name, 'team':team, 'position_rank':position_rank})
            num_rows_processed += 1
        else:
            break
    return projections

def get_projections(year=2021, positions=None):
    return remote_scrape(scrape_fp_projections)

