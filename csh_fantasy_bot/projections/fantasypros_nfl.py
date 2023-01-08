import json

# from web_scrape import remote_scrape
from csh_fantasy_bot.projections.web_scrape import remote_scrape
# https://www.fantasypros.com/nfl/rankings/half-point-ppr-cheatsheets.php
nfl_positions = ['QB', 'RB', 'WR', 'TE', 'K', 'D']
# fp_to_yahoo_team_name_map = {'Buffalo Bills':'Buffalo', 
#                             'Tampa Bay Buccaneers':'Tampa Bay',
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', 
#                             'Buffalo Bills':'Buffalo', }
#TODO handle types of scroring (STD, ppr, 1/2 ppr)

def scrape_fp_projections(driver):
    projections = []
    url = "https://www.fantasypros.com/nfl/rankings/half-point-ppr-cheatsheets.php"
    
    page = driver.get(url)
    # currently the ranking data is in a javascript variable ecrData.  look through the html
    # for the script block which defines that variable.  then convert it to a dict to 
    # extract the play list. 
    for el in driver.find_elements_by_tag_name('script'):
        if 'ecrData' in el.get_attribute('innerHTML'):
            ecr_script_block = el.get_attribute('innerHTML').splitlines()
            for line in ecr_script_block:
                if 'var ecrData' in line:
                    ecr_block = line
                    ecr_values = ecr_block.split('var ecrData =')[1]
                    ecr_values_short = ecr_values[:len(ecr_values)-1]
                    my_dict = json.loads(ecr_values_short)['players']
                    for player_row in my_dict:
                        rank = player_row['rank_ecr']
                        name = player_row['player_name']
                        team = player_row['player_team_id']
                        position_rank = player_row['pos_rank']
                    
                        projections.append({'fp_rank': rank, 'name':name, 'team':team, 'position_rank':position_rank})
                    break

    return projections

def get_projections(year=2021, positions=None):
    return remote_scrape(scrape_fp_projections)




if __name__ == '__main__':
    projections = get_projections(2022)