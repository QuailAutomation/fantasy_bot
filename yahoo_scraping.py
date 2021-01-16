from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys

import time, re, csv, sys, random

from csh_fantasy_bot import bot

# import settings
import settings

RE_REMOVE_HTML = re.compile('<.+?>')

SLEEP_SECONDS = 2
END_WEEK = 17
PAGES_PER_WEEK = 10
YAHOO_RESULTS_PER_PAGE = 25 # Static but used to calculate offsets for loading new pages

class YahooProjections:
    def __init__(self, league_id, scoring_categories) -> None:
        super().__init__()
        self.league_id = league_id
        self.league_suffix = league_id.split('.')[-1]
        self.XPATH_MAP = {
        'name': 'td[contains(@class,"player")]/div/div/div[contains(@class,"ysf-player-name")]/a',
        'position': 'td[contains(@class,"player")]/div/div/div[contains(@class,"ysf-player-name")]/span',
        'id': 'td[contains(@class,"player")]/div/div/span/a',
        'GP': 'td[6]',
        'preseason_rank': 'td[7]',
        'current_rank': 'td[8]'}

        for num, cat in enumerate(scoring_categories):
            self.XPATH_MAP[cat] = f"td[{10 + num}]"

        self.fields = ['id', 'name', 'position', 'team', 'preseason_rank', 'current_rank','GP'] + scoring_categories

    def process_stats_row(self, stat_row):
        stats_item = {}
        for col_name, xpath in self.XPATH_MAP.items():
            stats_item[col_name] = RE_REMOVE_HTML.sub('', stat_row.find_element_by_xpath(xpath).get_attribute('innerHTML'))
        # Custom logic for team, position, and opponent
        # stats_item['opp'] = stats_item['opp'].split(' ')[-1]
        team, position = stats_item['position'].split(' - ')
        stats_item['position'] = position
        stats_item['team'] = team

        stats_item['id'] = stat_row.find_element_by_xpath('td[contains(@class,"player")]/div/div/span/a').get_attribute('data-ys-playerid')
        return stats_item

    def process_page(self, driver, cnt):
        print('Getting stats for count', cnt)

        # url = 'http://football.fantasysports.yahoo.com/hockey/%s/players?status=A&pos=O&cut_type=9&stat1=S_PW_%d&myteam=0&sort=PR&sdir=1&count=%d' % (str(settings.YAHOO_LEAGUEID), week, cnt)
        url = 'https://hockey.fantasysports.yahoo.com/hockey/%s/players?status=A&pos=P&cut_type=33&stat1=S_PSR&sort=AR&sdir=1&count=%d' % (str(self.league_suffix),  cnt)
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
        username.send_keys(settings.YAHOO_USERNAME)
        driver.find_element_by_id("login-signin").send_keys(Keys.RETURN)

        time.sleep(SLEEP_SECONDS)

        password = driver.find_element_by_name('password')
        password.send_keys(settings.YAHOO_PASSWORD)
        driver.find_element_by_id("login-signin").send_keys(Keys.RETURN)
        time.sleep(SLEEP_SECONDS)

    def write_stats(self, stats, out):
        print('Writing to file', out)
        with open(out, 'w') as f:
            w = csv.DictWriter(f, delimiter=',', fieldnames=self.fields)
            w.writeheader()
            w.writerows(stats)

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
                time.sleep(SLEEP_SECONDS * 5)
                page_stats = self.process_page(driver, cnt)
            stats.extend(page_stats)

        self.write_stats(stats, outfile)

        driver.close()

def generate_predictions(league_id):
    outfile = f'yahoo-projections-stats-{league_id}.csv'
    manager: bot.ManagerBot = bot.ManagerBot(league_id=league_id)

    scoring_categories = manager.lg.scoring_categories()
    y_projections = YahooProjections(league_id, scoring_categories)
    y_projections.get_stats(outfile, league_id, scoring_categories)

if __name__ == '__main__':
    # league_id = "403.l.41177"
    league_id = "403.l.18782"
    # league_id = "396.l.53432"
    league_id = "403.l.41177"

    generate_predictions(league_id)