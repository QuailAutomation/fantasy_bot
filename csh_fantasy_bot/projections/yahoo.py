from enum import Enum
import time
import logging
import random
import pandas as pd

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
try: 
    import chromedriver_binary 
except ImportError:
    pass

from yahoo_fantasy_api import League
from csh_fantasy_bot.docker_utils import get_docker_secret
from csh_fantasy_bot.projections import yahoo_scrape_config as yc

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
SLEEP_SECONDS = 1

class PredictionType(Enum):
    days_7 = "S_PS7" # S_PS7 or S_PSR
    days_14 = "S_PS14"
    rest_season = "S_PSR"

def scrape(league:League, num_pages=1, offset_size=1, **args):

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

        driver =  webdriver.Remote("http://192.168.1.230:3001/webdriver", chrome_options.to_capabilities())
        
        # driver = webdriver.Chrome(chrome_options=chrome_options)
        driver.set_page_load_timeout(6000)

        print("Logging in")
        login(driver)

        time.sleep(SLEEP_SECONDS)

        stats = None
        for cnt in range(0, num_pages, offset_size):
            print(f"cnt is:{cnt}")
            try:
                page_stats = process_page(driver, cnt, league, args)
            except Exception as e:
                print('Failed to process page, sleeping and retrying', e)
                time.sleep(SLEEP_SECONDS * 5)
                page_stats = process_page(driver, cnt, args)
            if cnt == 0:
                stats = page_stats
            else:
                stats.extend(page_stats)
            
        driver.close()
        
        return stats

def login(self, driver):
    driver.get("https://login.yahoo.com/")
    # driver.get_screenshot_as_file('./pre-user.png')
    username = driver.find_element_by_name('username')
    LOG.info(f"Setting username: {YAHOO_USERNAME}")
    username.send_keys(YAHOO_USERNAME)
    driver.find_element_by_id("login-signin").send_keys(Keys.RETURN)

    time.sleep(SLEEP_SECONDS)
    
    # driver.get_screenshot_as_file('./pre-password.png')

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
        # driver.get_screenshot_as_file('./skip.png')
        pick_account = driver.find_element_by_name("username")
        pick_account.click()
        time.sleep(SLEEP_SECONDS)
        # driver.get_screenshot_as_file('./picked-account.png')
    
    time.sleep(SLEEP_SECONDS)


def get_projections_df(league: League, projection_length:PredictionType=None, positions=None):
    
    if projection_length is None:
        projection_length = PredictionType.rest_season

    if positions is None:
        positions = ['O']
    
    game_code = league.settings()['game_code']
    projections = []
    for player_type in  positions: #, 'K', 'O' ]:
        print(f"Processing: {player_type}")
        n_pages_scrape = yc.scraping_config[game_code][player_type]['num_pages_scrape']
        stats = scrape(projection_length=projection_length, num_pages=n_pages_scrape* 25, offset_size=25, scrape_info=yc[game_code][player_type]['scoring_stats'], season_status=league.settings()['draft_status'])
        df = pd.DataFrame.from_dict(stats)
        if 'id' in df.columns:
            df.rename(columns={"id": "player_id"}, inplace=True)
        projections.append(df)
    
    return pd.concat(projections, axis=0, ignore_index=True)

def process_page(driver, cnt, url, stat_col_mapping, args):
    LOG.debug('Getting stats for count', cnt)

    url = f'https://football.fantasysports.yahoo.com/f1/{self.league_suffix}/players?status=ALL&pos={args["scrape_info"]["stat_code"]}&stat1={args["projection_length"]}&sort=AR&sdir=1&count={cnt}'

    driver.get(url)
    # stat_col_mapping = self.column_nums_for_stats(driver, scrape_info_stats_map[args['season_status']][args['scrape_info']['stat_code']])
    base_xpath = "//div[contains(concat(' ',normalize-space(@class),' '),' players ')]/table/tbody/tr"

    rows = driver.find_elements_by_xpath(base_xpath)

    stats = []
    for row in rows:
        stats_item = process_stats_row(row, stat_col_mapping, args)
        stats.append(stats_item)

    driver.find_element_by_tag_name('body').send_keys(Keys.END)

    LOG.debug('Sleeping for', SLEEP_SECONDS)
    time.sleep(random.randint(SLEEP_SECONDS, SLEEP_SECONDS * 2))
    return stats

def process_stats_row(stat_row, stats_mapping, args):
    stats_item = {}
    for stat, col_number in stats_mapping.items():
        if 'name' == stat:
            # special case requires parsing
            stats_item['name'] = stat_row.find_element_by_xpath('td[contains(@class,"player")]/div/div/div[contains(@class,"ysf-player-name")]/a').text
            stats_item['team'], stats_item['position'] = stat_row.find_element_by_xpath('td[contains(@class,"player")]/div/div/div[contains(@class,"ysf-player-name")]/span').text.split(' - ')
            # look at add to watch column and extract the 'player_id'
            stats_item['player_id']  = int(stat_row.find_element_by_xpath("td[1]/div/a").get_attribute('name').split('-')[-1])
        else:
            try:
                val = float(stat_row.find_element_by_xpath(f'td[{col_number}]').text)
                if val.is_integer():
                    val = int(val)
                stats_item[stat] = val
                
            except Exception as e:
                print(e)

    return stats_item

if __name__ == '__main__':
    pass