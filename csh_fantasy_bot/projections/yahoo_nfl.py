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
    def __init__(self, league) -> None:
        self.league = league
        self.league_id = league.league_id
        self.league_suffix = league.league_id.split('.')[-1]
        
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

        driver =  webdriver.Remote("http://192.168.1.230:3001/webdriver", chrome_options.to_capabilities())
        
        # driver = webdriver.Chrome(chrome_options=chrome_options)
        driver.set_page_load_timeout(6000)

        print("Logging in")
        self.login(driver)

        time.sleep(SLEEP_SECONDS)

        stats = None
        for cnt in range(0, num_pages, offset_size):
            print(f"cnt is:{cnt}")
            try:
                page_stats = self.process_page(driver, cnt, args)
            except Exception as e:
                print('Failed to process page, sleeping and retrying', e)
                time.sleep(SLEEP_SECONDS * 5)
                page_stats = self.process_page(driver, cnt, args)
            if cnt == 0:
                stats = page_stats
            else:
                stats.extend(page_stats)
            
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
    def __init__(self, league) -> None:
        super().__init__(league)

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
scrape_info_stats_map = {"predraft": {"K":{
    'name': 'Kickers',
    'GP': 'GP*',
    'bye': 'Bye',
    'fan_points': 'Fan Pts',
    'overall_rank': 'O-Rank',
},
"DEF":{
    'name': 'Defense/Special Teams',
    'GP': 'GP*',
    'bye': 'Bye',
    'fan_points': 'Fan Pts',
    'overall_rank': 'O-Rank',
},
"O":{
    'name': 'Offense',
    'GP': 'GP*',
    'bye': 'Bye',
    'fan_points': 'Fan Pts',
    'overall_rank': 'O-Rank',
}
}, "postdraft": {"K":{
    'name': 'Kickers',
    'GP': 'GP*',
    'bye': 'Bye',
    'fan_points': 'Fan Pts',
    'preseason': 'Pre-Season',
    'actual_rank': 'Actual'
},
"DEF":{
    'name': 'Defense/Special Teams',
    'GP': 'GP*',
    'bye': 'Bye',
    'fan_points': 'Fan Pts',
    'preseason': 'Pre-Season',
    'actual_rank': 'Actual'
},
"O":{
    'name': 'Offense',
    'GP': 'GP*',
    'bye': 'Bye',
    'fan_points': 'Fan Pts',
    'preseason': 'Pre-Season',
    'actual_rank': 'Actual'
}

}
}

scrape_info_for_position_type = {"O":{'n_scrape_pages':20, 'stat_code':'O', 'scoring_stats':{
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
        'receiving_tds': 'td[22]',}},
        "K":{'n_scrape_pages':2,'stat_code':'K', 'scoring_stats':{
        'name': 'td[contains(@class,"player")]/div/div/div[contains(@class,"ysf-player-name")]/a',
        'position': 'td[contains(@class,"player")]/div/div/div[contains(@class,"ysf-player-name")]/span',
        'player_id': 'td[contains(@class,"player")]/div/div/span/a',
        'GP': 'td[5]',
        'Bye': 'td[6]',
        'fan_points': 'td[7]',
        'overall_rank': 'td[8]',
        'percent_rostered': 'td[10]'}
        },
        "D":{'n_scrape_pages':2, 'stat_code':'DEF', 'scoring_stats':{
        'name': 'td[contains(@class,"player")]/div/div/div[contains(@class,"ysf-player-name")]/a',
        'position': 'td[contains(@class,"player")]/div/div/div[contains(@class,"ysf-player-name")]/span',
        'player_id': 'td[contains(@class,"player")]/div/div/span/a',
        'GP': 'td[5]',
        'Bye': 'td[6]',
        'fan_points': 'td[7]',
        'overall_rank': 'td[8]',
        'percent_rostered': 'td[10]'}
        }}
class YahooProjectionScraper(YahooFantasyScraper):
    def __init__(self, league, scoring_categories) -> None:
        super().__init__(league)
        
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

        self.fields = ['player_id', 'name', 'position', 'team', 'overall_rank', 'current_rank','GP'] + scoring_categories

    def column_nums_for_stats(self, web_driver, stats):
        """[summary]

        Args:
            web_driver ([webdriver]): [selenium webdriver containing page source]
            stats ([list]): [stats of interest]
        
        Returns:
            [dict]: stat:column_number(int)
        """
        col_xpath = "//div[contains(concat(' ',normalize-space(@class),' '),' players ')]/table/thead/tr[contains(@class, 'Alt Last')]/th"
        columns = web_driver.find_elements_by_xpath(col_xpath)
        return_value = {}
        for index, column in enumerate(columns):
            # strip out sort order indicator if there
            clean_col_text = column.text.strip('\ue002')
            if clean_col_text in stats.values():
                return_value[list(stats.keys())[list(stats.values()).index(clean_col_text)]] = index + 1
        
        assert len(return_value) == len(stats), f"Column reference for status are unequal, stats len: {len(stats)}, len x-ref: {len(return_value)}" 
        return return_value

    def process_page(self, driver, cnt, args):
        LOG.debug('Getting stats for count', cnt)

        url = f'https://football.fantasysports.yahoo.com/f1/{self.league_suffix}/players?status=ALL&pos={args["scrape_info"]["stat_code"]}&stat1={args["projection_length"]}&sort=AR&sdir=1&count={cnt}'

        driver.get(url)
        stat_col_mapping = self.column_nums_for_stats(driver, scrape_info_stats_map[args['season_status']][args['scrape_info']['stat_code']])
        base_xpath = "//div[contains(concat(' ',normalize-space(@class),' '),' players ')]/table/tbody/tr"

        rows = driver.find_elements_by_xpath(base_xpath)

        stats = []
        for row in rows:
            stats_item = self.process_stats_row(row, stat_col_mapping, args)
            stats.append(stats_item)

        driver.find_element_by_tag_name('body').send_keys(Keys.END)

        LOG.debug('Sleeping for', SLEEP_SECONDS)
        time.sleep(random.randint(SLEEP_SECONDS, SLEEP_SECONDS * 2))
        return stats

    def process_stats_row(self, stat_row, stats_mapping, args):
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

    

    def get_projections_df(self, projection_length, season_status='postdraft'):
        projections = []

        for player_type in  ['O', 'K', 'D']:
            print(f"Processing: {player_type}")
            n_pages_scrape = scrape_info_for_position_type[player_type]['n_scrape_pages']
            stats = self.scrape(projection_length=projection_length, num_pages=n_pages_scrape* 25, offset_size=25, scrape_info=scrape_info_for_position_type[player_type], season_status=season_status)
            df = pd.DataFrame.from_dict(stats)
            if 'id' in df.columns:
                df.rename(columns={"id": "player_id"}, inplace=True)
            projections.append(df)
        
        return pd.concat(projections, axis=0, ignore_index=True)


class PredictionType(Enum):
    days_7 = "S_PS7" # S_PS7 or S_PSR
    days_14 = "S_PS14"
    rest_season = "S_PSR_2021"

def category_name_list(raw_stat_categories, position_type=['P']):
        """Return list of categories that count for scoring."""
        return [stat['display_name'] for stat in raw_stat_categories if stat['position_type'] in position_type]

def retrieve_draft_order(lg):
    draft_scrape =  YahooDraftScraper(lg).scrape(fantasy_year=int(lg.settings()['season']))
    draft_results = {}
    draft_results['status'] = lg.settings()['draft_status']
    if 'draft_time'  in lg.settings().keys():
        draft_results['draft_time'] =  datetime.datetime.fromtimestamp(int(lg.settings().get('draft_time', None)))
    else:
        # draft time not set yet.  Default to day of season start
        draft_results['draft_time'] = datetime.datetime.fromisoformat(lg.settings()['start_date'])

    draft_results['keepers'] = {}
    draft_results['draft_picks'] = {}
    # return val is keyed on team name, lets switch that to team key
    # make a map of team name : team_key
    name_to_key_map = {team['name']:team['team_key'] for team in lg.teams()}

    # Seperate keepers from drafted players
    for team, draft_picks in draft_scrape.items():
        team_picks = []
        team_keepers = []
        for pick in draft_picks:
            if isinstance(pick, dict) and pick['is_keeper'] == True:
                team_keepers.append(pick)
            else:
                team_picks.append(pick)
        draft_results['keepers'][name_to_key_map[team]] = team_keepers
        draft_results['draft_picks'][name_to_key_map[team]] = team_picks

    # figure out num keepers and rounds by looking at first teams breakdown
    if draft_scrape:
        first_team = next(iter(draft_results['draft_picks']))
        draft_results['num_keepers'] = len(draft_results['keepers'][first_team])
        draft_results['num_rounds'] = len(draft_results['draft_picks'][first_team])
    return draft_results

def generate_predictions(lg, predition_type=PredictionType.days_14):

    scoring_categories = category_name_list(lg.stat_categories(),position_type=['O'])

    y_projections = YahooProjectionScraper(lg, scoring_categories)
    projections = y_projections.get_projections_df(predition_type.value)
    
    return projections

if __name__ == '__main__':
    # league_id = "403.l.41177"
    league_id = "403.l.18782"
    # league_id = "396.l.53432"
    league_id = "403.l.41177"

    generate_predictions(league_id)