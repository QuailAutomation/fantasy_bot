import pandas as pd
import datetime
from enum import Enum

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
try: 
    import chromedriver_binary 
except ImportError:
    pass
import time, re, csv, sys, random

from csh_fantasy_bot.league import FantasyLeague
from csh_fantasy_bot.nhl import find_teams_playing
from nhl_scraper.nhl import Scraper

from csh_fantasy_bot.docker_utils import get_docker_secret


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
    YAHOO_USERNAME = get_yahoo_credential("YAHOO_PASSWORD")


RE_REMOVE_HTML = re.compile('<.+?>')

SLEEP_SECONDS = 1
END_WEEK = 17
PAGES_PER_WEEK = 40
YAHOO_RESULTS_PER_PAGE = 25 # Static but used to calculate offsets for loading new pages

nhl_team_mappings = {'LA': 'LAK', 'Ott': 'OTT', 'Bos': 'BOS', 'SJ': 'SJS', 'Anh': 'ANA', 'Min': 'MIN',
                    'Nsh': 'NSH', 'Tor': 'TOR', 'StL': 'STL', 'Det': 'DET', 'Edm': 'EDM', 'Chi': 'CHI', 'TB': 'TBL',
                    'Fla': 'FLA', 'Dal': 'DAL', 'Van': 'VAN', 'NJ': 'NJD', 'Mon': 'MTL', 'Ari': 'ARI', 'Wpg': 'WPG',
                    'Pit': 'PIT', 'Was': 'WSH', 'Cls': 'CBJ', 'Col': 'COL', 'Car': 'CAR', 'Buf': 'BUF', 'Cgy': 'CGY',
                    'Phi': 'PHI'}

class YahooProjectionScraper:
    def __init__(self, league_id, scoring_categories) -> None:
        super().__init__()
        self.league_id = league_id
        self.league_suffix = league_id.split('.')[-1]
        self.XPATH_MAP = {
        'name': 'td[contains(@class,"player")]/div/div/div[contains(@class,"ysf-player-name")]/a',
        'position': 'td[contains(@class,"player")]/div/div/div[contains(@class,"ysf-player-name")]/span',
        'player_id': 'td[contains(@class,"player")]/div/div/span/a',
        'GP': 'td[6]',
        'preseason_rank': 'td[7]',
        'current_rank': 'td[8]'}

        for num, cat in enumerate(scoring_categories):
            self.XPATH_MAP[cat] = f"td[{10 + num}]"

        self.fields = ['player_id', 'name', 'position', 'team', 'preseason_rank', 'current_rank','GP'] + scoring_categories

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

    def process_page(self, driver, cnt, projection_length="S_PSR"):
        print('Getting stats for count', cnt)

        url = f'https://hockey.fantasysports.yahoo.com/hockey/{self.league_suffix}/players?status=ALL&pos=P&cut_type=33&stat1={projection_length}&sort=AR&sdir=1&count={cnt}'

        driver.get(url)

        base_xpath = "//div[contains(concat(' ',normalize-space(@class),' '),' players ')]/table/tbody/tr"

        rows = driver.find_elements_by_xpath(base_xpath)

        stats = []
        for row in rows:
            stats_item = self.process_stats_row(row)
            stats.append(stats_item)

        driver.find_element_by_tag_name('body').send_keys(Keys.END)

        print('Sleeping for', SLEEP_SECONDS)
        time.sleep(random.randint(SLEEP_SECONDS, SLEEP_SECONDS * 2))
        return stats

    def login(self, driver):
        driver.get("https://login.yahoo.com/")

        username = driver.find_element_by_name('username')
        username.send_keys(YAHOO_USERNAME)
        driver.find_element_by_id("login-signin").send_keys(Keys.RETURN)

        time.sleep(SLEEP_SECONDS)

        password = driver.find_element_by_name('password')
        password.send_keys(YAHOO_PASSWORD)
        driver.find_element_by_id("login-signin").send_keys(Keys.RETURN)
        time.sleep(SLEEP_SECONDS)

    def write_stats(self, stats, out):
        print('Writing to file', out)
        with open(out, 'w') as f:
            w = csv.DictWriter(f, delimiter=',', fieldnames=self.fields)
            w.writeheader()
            w.writerows(stats)

    def get_projections_df(self, projection_length):
        # projection_length = "S_PS14" # S_PS7 or S_PSR

        chrome_options = Options()
        # chrome_options.add_extension('chrome-ublock.crx')
        # chrome_options.add_argument("--enable-extensions")
    
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        # chrome_options.add_argument("window-size=1400,2100") 
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-background-timer-throttling')
        chrome_options.add_argument('--disable-breakpad')
        chrome_options.add_argument('--disable-component-extensions-with-background-pages')
        chrome_options.add_argument('--disable-extensions')
        # chrome_options.add_argument('')
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
        for cnt in range(0, PAGES_PER_WEEK*YAHOO_RESULTS_PER_PAGE, YAHOO_RESULTS_PER_PAGE):
            try:
                page_stats = self.process_page(driver, cnt, projection_length)
            except Exception as e:
                print('Failed to process page, sleeping and retrying', e)
                time.sleep(SLEEP_SECONDS * 5)
                page_stats = self.process_page(driver, cnt, projection_length)
            stats.extend(page_stats)
            
        driver.close()
        df = pd.DataFrame(stats, columns=self.fields)
        df.rename(columns={"id": "player_id"}, inplace=True)
        return df

    def get_stats(self, outfile, league_id, scoring_categories):

        chrome_options = Options()
        chrome_options.add_extension('chrome-ublock.crx')
        chrome_options.add_argument("--enable-extensions")

        driver = webdriver.Chrome(chrome_options=chrome_options)
        driver.set_page_load_timeout(30)

        print("Logging in")
        self.login(driver)

        time.sleep(SLEEP_SECONDS)

        stats = []
        for cnt in range(0, PAGES_PER_WEEK*YAHOO_RESULTS_PER_PAGE, YAHOO_RESULTS_PER_PAGE):
            try:
                page_stats = self.process_page(driver, cnt)
            except Exception as e:
                print('Failed to process page, sleeping and retrying', e)
                time.sleep(SLEEP_SECONDS * 1)
                page_stats = self.process_page(driver, cnt)
            stats.extend(page_stats)

        self.write_stats(stats, outfile)

        driver.close()


class PredictionType(Enum):
    days_7 = "S_PS7" # S_PS7 or S_PSR
    days_14 = "S_PS14"
    rest_season = "S_PSR"

def generate_predictions(league_id, predition_type=PredictionType.days_14):
    
    lg = FantasyLeague(league_id)
    scoring_categories = lg.scoring_categories()

    y_projections = YahooProjectionScraper(league_id, scoring_categories)
    projections = y_projections.get_projections_df(predition_type.value)
    
    projections["team"].replace(nhl_team_mappings, inplace=True)

    
    nhl_scraper= Scraper()
    nhl_teams = nhl_scraper.teams()

    nhl_teams.set_index("id")
    nhl_teams.rename(columns={'name': 'team_name'}, inplace=True)

    all_players= projections.merge(nhl_teams, left_on='team', right_on='abbrev')
    all_players.rename(columns={'id': 'team_id'}, inplace=True)
    
    # GP is incorrect for 7 and 14 day predictions, let's get nhl schedule and fix
    game_day = datetime.date.today()
    if predition_type != PredictionType.rest_season:
        if predition_type == PredictionType.days_7:
            num_days = 7
        else:
            num_days = 14
        games = find_teams_playing(game_day, num_days)
        all_players['GP'] = all_players["team_id"].map(games)

    # let's return projections per game
    for stat in scoring_categories:
        all_players[stat] = pd.to_numeric(all_players[stat], downcast="float")
        all_players[stat] = all_players[stat] / all_players['GP']

    # y_projections.get_stats(outfile, league_id, scoring_categories)
    return all_players

class YahooPredictions:
    def __init__(self, league_id, predition_type=PredictionType.days_14) -> None:
        
        lg = FantasyLeague(league_id)
        self.scoring_categories = lg.scoring_categories()

        y_projections = YahooProjectionScraper(league_id, self.scoring_categories)
        projections = y_projections.get_projections_df(predition_type.value)
        # if no projection, then zero
        projections.replace('-', 0, inplace=True)
        projections["team"].replace(nhl_team_mappings, inplace=True)

        nhl_scraper= Scraper()
        nhl_teams = nhl_scraper.teams()
        nhl_teams.set_index("id")
        nhl_teams.rename(columns={'name': 'team_name'}, inplace=True)

        all_players= projections.merge(nhl_teams, left_on='team', right_on='abbrev')
        all_players.rename(columns={'id': 'team_id'}, inplace=True)
        
        # GP is incorrect for 7 and 14 day predictions, let's get nhl schedule and fix
        game_day = datetime.date.today()
        if predition_type != PredictionType.rest_season:
            if predition_type == PredictionType.days_7:
                num_days = 7
            else:
                num_days = 14
            games = find_teams_playing(game_day, num_days)
            all_players['GP'] = all_players["team_id"].map(games)

        # let's return projections per game
        for stat in self.scoring_categories:
            all_players[stat] = pd.to_numeric(all_players[stat], downcast="float")
            all_players[stat] = all_players[stat] / (all_players['GP'] + .0000001)

        # y_projections.get_stats(outfile, league_id, scoring_categories)
        self.all_players = all_players.set_index('player_id')

    def predict(self, roster):
        return roster.merge(self.all_players[self.scoring_categories], on="player_id")


if __name__ == '__main__':
    # league_id = "403.l.41177"
    league_id = "403.l.18782"
    # league_id = "396.l.53432"
    league_id = "403.l.41177"

    generate_predictions(league_id)