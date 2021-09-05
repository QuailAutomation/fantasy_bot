import pandas as pd
import datetime
import logging
import os
from enum import Enum

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
try: 
    import chromedriver_binary 
except ImportError:
    pass
import time, re, csv, sys, random

from csh_fantasy_bot.docker_utils import get_docker_secret
from csh_fantasy_bot.google_email import get_last_yahoo_confirmation

LOG = logging.getLogger(__name__)

def get_yahoo_credential(property, missing_val=None):
    from pathlib import Path
    import configparser
    config = configparser.ConfigParser()
    config.read(f'{Path.home()}/.yahoo/credentials')
    return config['main'][property]


YAHOO_USERNAME=get_docker_secret("YAHOO_USERNAME")
if not YAHOO_USERNAME:
    YAHOO_USERNAME = get_yahoo_credential("YAHOO_USERNAME")

YAHOO_PASSWORD=get_docker_secret("YAHOO_PASSWORD")
if not YAHOO_PASSWORD:
    YAHOO_PASSWORD = get_yahoo_credential("YAHOO_PASSWORD")


RE_REMOVE_HTML = re.compile('<.+?>')

SLEEP_SECONDS = 1
END_WEEK = 17
PAGES_PER_WEEK = 10
YAHOO_RESULTS_PER_PAGE = 25 # Static but used to calculate offsets for loading new pages


class YahooFantasyScraper:
    def __init__(self, league_id) -> None:
        self.league_id = league_id
        self.league_suffix = league_id.split('.')[-1]

        
    def scrape(self, num_pages=1, offset_size=1, **args):

        chrome_options = Options()
    
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-background-timer-throttling')
        chrome_options.add_argument('--disable-breakpad')
        chrome_options.add_argument('--disable-component-extensions-with-background-pages')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-features=TranslateUI,BlinkGenPropertyTrees')
        chrome_options.add_argument('--disable-ipc-flooding-protection')
        chrome_options.add_argument('--disable-renderer-backgrounding')
        chrome_options.add_argument('--enable-features=NetworkService,NetworkServiceInProcess')
        chrome_options.add_argument('--force-color-profile=srgb')
        chrome_options.add_argument('--hide-scrollbars')
        chrome_options.add_argument('--metrics-recording-only')
        chrome_options.add_argument('--mute-audio')
        chrome_options.add_argument("--disable-logging")
        chrome_options.add_argument("--log-level=3")

        driver =  webdriver.Remote("http://192.168.1.20:3001/webdriver", chrome_options.to_capabilities())
        
        # driver = webdriver.Chrome(chrome_options=chrome_options)
        driver.set_page_load_timeout(6000)

        print("Logging in")
        self.login(driver)

        time.sleep(SLEEP_SECONDS)

        stats = []
        for cnt in range(0, num_pages, offset_size):
            try:
                page_stats = self.process_page(driver, cnt, args)
            except Exception as e:
                print('Failed to process page, sleeping and retrying', e)
                time.sleep(SLEEP_SECONDS * 5)
                page_stats = self.process_page(driver, cnt, args)
            stats.append(page_stats)
            
        driver.close()
        
        return stats

    def login(self, driver):
        driver.get("https://login.yahoo.com/")
        driver.get_screenshot_as_file('./pre-user.png')
        username = driver.find_element_by_name('username')
        LOG.info(f"Setting username: {YAHOO_USERNAME}")
        username.send_keys(YAHOO_USERNAME)
        driver.find_element_by_id("login-signin").send_keys(Keys.RETURN)

        time.sleep(SLEEP_SECONDS)
        
        driver.get_screenshot_as_file('./pre-password.png')
        

        try:
            password = driver.find_element_by_name('password')
            password.send_keys(YAHOO_PASSWORD)
            password.send_keys(Keys.RETURN)
        except Exception as e:
            verification_code = self.retrieve_verification_code()
            # should loop for 5 mins and look for file verification.txt.  load that and submit
            verification = driver.find_element_by_id("verification-code-field")
            verification.send_keys(verification_code)
            verification.send_keys(Keys.RETURN)

            time.sleep(SLEEP_SECONDS)
            driver.get_screenshot_as_file('./skip.png')
            pick_account = driver.find_element_by_name("username")
            pick_account.click()
            time.sleep(SLEEP_SECONDS)
            driver.get_screenshot_as_file('./picked-account.png')
        
        time.sleep(SLEEP_SECONDS)

class YahooDraftScraper(YahooFantasyScraper):
    def __init__(self, league_id) -> None:
        super().__init__(league_id)

    def process_page(self, driver, cnt, args):

        url = None
        if args['fantasy_year'] == datetime.datetime.now().year:
            url = f'https://football.fantasysports.yahoo.com/f1/{self.league_suffix}/draftresults?drafttab=team'
        else:
            url = f'https://football.fantasysports.yahoo.com/{args["fantasy_year"]}/f1/{self.league_suffix}/draftresults?activity=draftresults&drafttab=team'
        # for 2019
        # 
            
        driver.get(url)
        # get team tables
        base_xpath = '//*[@id="drafttables"]//table'
        rows = driver.find_elements_by_xpath(base_xpath)

        return_value = {}
        for row in rows:
            stats_item = self.process_draft_page(row)
            return_value[stats_item[0]] =  stats_item[1]
            

        driver.find_element_by_tag_name('body').send_keys(Keys.END)

        return return_value
    
    def process_draft_page(self, stat_row):
        try:
            keeper_icon_text = '\ue03e'
            stats_item = {}
            team_picks=[]
            team_name = stat_row.find_element_by_xpath('./thead/tr/th').text
            picks = stat_row.find_elements_by_xpath('./tbody/tr')
            for pick_row in picks:
                pick_info = pick_row.find_element_by_xpath('./td[contains(@class,"player")]').text
                if 'Pick #' in pick_info:
                    team_picks.append(int(pick_info.split('Pick #')[-1])) 
                else:
                    pick_data = {}
                    try:
                        pick_num_text = pick_row.find_element_by_xpath('./td[contains(@class,"pick")]').text.strip('()')
                        pick_data['number'] = int(pick_row.find_element_by_xpath('./td[contains(@class,"pick")]').text.strip('()'))
                    except:
                        pass
                        print("didnt work")
                        # assert False, f"Cannot figure out pick number: {pick_row.find_element_by_xpath('./td[contains(@class,\"pick\")]').text}"
                    pick_data['name'] = pick_info.split(keeper_icon_text)[0].strip()
                    try:
                        pick_data['team'], pick_data['position'] = pick_info.split(keeper_icon_text)[-1].strip(' ()').split(' - ')
                        
                    except ValueError:
                        pass
                        # this is ok, prior years do not include this info
                    pick_data['is_keeper'] =  keeper_icon_text in pick_info
                    team_picks.append(pick_data)

            return (team_name, team_picks)
        except Exception as e:
            print(e)

stats_for_position_type = {"O":{
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
        'receiving_tds': 'td[22]',},
        "K":{
        'name': 'td[contains(@class,"player")]/div/div/div[contains(@class,"ysf-player-name")]/a',
        'position': 'td[contains(@class,"player")]/div/div/div[contains(@class,"ysf-player-name")]/span',
        'player_id': 'td[contains(@class,"player")]/div/div/span/a',
        'GP': 'td[6]',
        'Bye': 'td[7]',
        'fan_points': 'td[8]',
        'overall_rank': 'td[9]',
        'percent_rostered': 'td[11]'}
        }
class YahooProjectionScraper(YahooFantasyScraper):
    def __init__(self, league_id, scoring_categories) -> None:
        super().__init__(league_id)
        
        self.XPATH_MAP = {
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

        # for num, cat in enumerate(scoring_categories):
        #     self.XPATH_MAP[cat] = f"td[{10 + num}]"

        self.fields = ['player_id', 'name', 'position', 'team', 'overall_rank', 'current_rank','GP'] + scoring_categories

    def process_page(self, driver, cnt, args):
        LOG.debug('Getting stats for count', cnt)

        url = f'https://football.fantasysports.yahoo.com/f1/{self.league_suffix}/players?status=ALL&pos=O&stat1={args["projection_length"]}&sort=AR&sdir=1&count={cnt}'

        driver.get(url)

        base_xpath = "//div[contains(concat(' ',normalize-space(@class),' '),' players ')]/table/tbody/tr"

        rows = driver.find_elements_by_xpath(base_xpath)

        stats = []
        for row in rows:
            stats_item = self.process_stats_row(row)
            stats.append(stats_item)

        driver.find_element_by_tag_name('body').send_keys(Keys.END)

        LOG.debug('Sleeping for', SLEEP_SECONDS)
        time.sleep(random.randint(SLEEP_SECONDS, SLEEP_SECONDS * 2))
        return stats

    def process_stats_row(self, stat_row):
        stats_item = {}
        for col_name, xpath in self.XPATH_MAP.items():
            stats_item[col_name] = RE_REMOVE_HTML.sub('', stat_row.find_element_by_xpath(xpath).get_attribute('innerHTML'))
        # Custom logic for team, position, and opponent
        # stats_item['opp'] = stats_item['opp'].split(' ')[-1]
        team, position = stats_item['position'].split(' - ')
        stats_item['position'] = position
        stats_item['team'] = team

        stats_item['player_id'] = int(stat_row.find_element_by_xpath('td[contains(@class,"player")]/div/div/span/a').get_attribute('data-ys-playerid'))
        return stats_item

    

    def get_projections_df(self, projection_length):
       
        stats = self.scrape(projection_length=projection_length, num_pages=140, offset_size=25)
        # driver.close()
        df = pd.DataFrame.from_dict(stats) #pd.DataFrame(stats, columns=self.fields)
        df.rename(columns={"id": "player_id"}, inplace=True)
        return df



class PredictionType(Enum):
    days_7 = "S_PS7" # S_PS7 or S_PSR
    days_14 = "S_PS14"
    rest_season = "S_PSR_2021"

def category_name_list(raw_stat_categories, position_type=['P']):
        """Return list of categories that count for scoring."""
        return [stat['display_name'] for stat in raw_stat_categories if stat['position_type'] in position_type]

def retrieve_draft_order(lg):
    draft_scrape =  YahooDraftScraper(lg.league_id).scrape(fantasy_year=int(lg.settings()['season']))
    # return val is keyed on team name, lets switch that to team key
    # make a map of team name : team_key
    draft_results = {}
    draft_results['status'] = lg.settings()['draft_status']
    draft_results['draft_time'] =  datetime.datetime.fromtimestamp(int(lg.settings()['draft_time']))
    draft_results['keepers'] = {}
    draft_results['draft_picks'] = {}
    name_to_key_map = {team['name']:team['team_key'] for team in lg.teams()}

    # Seperate keepers from draft results
    for team, draft_picks in draft_scrape[0].items():
        team_picks = []
        team_keepers = []
        for pick in draft_picks:
            if isinstance(pick, dict):
                team_keepers.append(pick)
            else:
                team_picks.append(pick)
        draft_results['keepers'][name_to_key_map[team]] = team_keepers
        draft_results['draft_picks'][name_to_key_map[team]] = team_picks

    # figure out num keepers and rounds by looking at first teams breakdown
    first_team = next(iter(draft_results['draft_picks']))
    draft_results['num_keepers'] = len(draft_results['keepers'][first_team])
    draft_results['num_rounds'] = len(draft_results['draft_picks'][first_team])
    return draft_results

def generate_predictions(lg, predition_type=PredictionType.days_14):
    player_types = ['O', 'K'] # , 'DEF'

    scoring_categories = category_name_list(lg.stat_categories(),position_type=['O'])

    y_projections = YahooProjectionScraper(lg.league_id, scoring_categories)
    projections = y_projections.get_projections_df(predition_type.value)
    
    return projections

if __name__ == '__main__':
    # league_id = "403.l.41177"
    league_id = "403.l.18782"
    # league_id = "396.l.53432"
    league_id = "403.l.41177"

    generate_predictions(league_id)