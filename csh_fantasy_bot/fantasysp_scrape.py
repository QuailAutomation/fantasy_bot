#!/usr/bin/python
#url = 'https://www.fantasysp.com/projections/hockey/daily/'
"""
A script that scrapes projections from ESPNs and outputs them to csv format.
It produces two files:
    espn.skaters.proj.csv   : Projections for all skaters
    espn.goalies.proj.csv   : Projections for all goalies
"""
from selenium import webdriver
from bs4 import BeautifulSoup
import time
import pandas as pd
from nhl_scraper.nhl import Scraper
html_file_location = ".cache/"


class ProjectionScraper:
    def __init__(self):
        pass

    def scrape(self):
        driver = webdriver.Chrome()
        driver.maximize_window()
        positions_to_scrape = ['C','LW','RW','D','G']
        file_names = []
        url = "https://www.fantasysp.com/projections/hockey/weekly/{}"
        try:
            for position_scraped in positions_to_scrape:

                driver.implicitly_wait(15)
                driver.get(url.format(position_scraped))

                time.sleep(5)
                fn = "{}fantasysp_weekly-{}.html"
                with open(fn.format(html_file_location, position_scraped), "w") as f:
                    soup = BeautifulSoup(driver.page_source, "lxml")
                    f.write(soup.prettify())
                    # file_names.append(fn.format(position_scraped))
        finally:
            driver.close()

        return None


class Parser:
    goalie_headings = ["GAA", "WIN%", "SHO%"]
    def __init__(self, positions=None):
        # which positions to scrape from fantasysp
        if positions is not None:
            self.positions = positions
        else:
            self.positions = ['C','LW','RW','D','G']




        player_headings = ["G", "A", "SOG", "+/-", "HIT", "PIM", "FOW"]
        headings = ["Name", "Tm", "Pos", "GAMES"]
        df = pd.DataFrame(data=[], columns=headings)
        index_offset = 0
        for position in self.positions:
            print("Processing: {}".format(position))
            file_name = "{}fantasysp_weekly-{}.html".format(html_file_location, position)

            with open(file_name, "rb") as f:
                soup = BeautifulSoup(f, "lxml")
                table = soup.find("table", {"class": "table sortable table-clean table-add-margin table-fixed"})
                table_body = table.find('tbody')

                rows = table_body.find_all('tr')
                for i, row in enumerate(rows):
                    name_base = row.find_all('td')[1].text.strip().split("\n")
                    # name_base = row.find_all('td')[1].find_all('span')
                    name = name_base[0].strip()
                    tm = name_base[3].strip()
                    pos = name_base[6].strip()

                    games_base = row.find_all('td')[2].text.strip().split("\n")[0]
                    for i, c in enumerate(games_base):
                        if not c.isdigit():
                            break
                    num_games = int(games_base[:i])
                    if position != 'G':
                        goals = float(row.find("td", {"class": "proj-g"}).text.strip()) / num_games
                        assists = float(row.find("td", {"class": "proj-ast"}).text.strip()) / num_games
                        shots = float(row.find("td", {"class": "proj-sog"}).text.strip()) / num_games
                        plus_minus = float(row.find("td", {"class": "proj-plusminus"}).text.strip()) / num_games
                        hit = float(row.find("td", {"class": "proj-hit"}).text.strip()) / num_games
                        pim = float(row.find("td", {"class": "proj-pim"}).text.strip()) / num_games
                        fow = float(row.find("td", {"class": "proj-fow"}).text.strip()) / num_games

                        df = df.append(pd.DataFrame(
                            data=[[name, tm, pos, num_games, goals, assists, shots, plus_minus, hit, pim, fow]],
                            columns=headings + player_headings, index=[i + index_offset]))
                    else:
                        # goalie
                        # goalie_starting_status = 'Confirmed'
                        # if starting_goalies_df is not None:
                        #     goalie_starting_status = starting_goalies_df.query('goalie_name == {}'.format(name))
                        gaa = float(row.find("td", {"class": "proj-gaa"}).text.strip())
                        win_per_game = float(row.find("td", {"class": "proj-wins"}).text.strip()) / num_games
                        so_per_game = float(row.find("td", {"class": "proj-so"}).text.strip()) / num_games
                        df = df.append(pd.DataFrame(
                            data=[[name, tm, pos, num_games, gaa, win_per_game, so_per_game]],
                            columns= headings + Parser.goalie_headings, index=[i + index_offset]))
                stats = ["G", "A", "SOG", "+/-", "HIT", "PIM", "FOW"]
                # compute per game stats
                # for stat in stats:
                #     df["{}-GAME".format(stat)] = df[stat].div(df["GAMES"])

        df['Tm'].replace("TB", "TBL", inplace=True)
        df['Tm'].replace("WAS", "WSH", inplace=True)
        df['Tm'].replace("SJ", "SJS", inplace=True)
        df['Tm'].replace("MON", "MTL", inplace=True)
        df['Tm'].replace("CLB", "CBJ", inplace=True)
        df['Tm'].replace("NJ", "NJD", inplace=True)
        df['Tm'].replace("LA", "LAK", inplace=True)

        self.ppool = df
        self.ppool.rename(columns={'Name': 'name'}, inplace=True)

    def predict(self, my_roster):
        """Build a dataset of hockey predictions for the week

                The pool of players is passed into this function through roster_const.
                It will generate a DataFrame for these players with their predictions.

                The returning DataFrame has rows for each player, and columns for each
                prediction stat.

                :param roster_cont: Roster of players to generate predictions for
                :type roster_cont: roster.Container object
                :return: Dataset of predictions
                :rtype: DataFrame
                """
        # Produce a DataFrame using preds as the base.  We'll filter out
        # all of the players not in roster_cont by doing a join of the two
        # data frames.  This also has the affect of attaching eligible
        # positions and Yahoo! player ID from the input player pool.
        self.nhl_scraper = Scraper()

        if 'team_id' not in my_roster.columns:
            # we must map in teams
            self._fix_yahoo_team_abbr(my_roster)
            nhl_teams = self.nhl_scraper.teams()
            nhl_teams.set_index("id")
            nhl_teams.rename(columns={'name': 'team_name'}, inplace=True)

            my_roster = my_roster.merge(nhl_teams, left_on='editorial_team_abbr', right_on='abbrev')
            my_roster.rename(columns={'id': 'team_id'}, inplace=True)

        df = pd.merge(my_roster, self.ppool[["G", "A", "SOG", "+/-", "HIT", "PIM", "FOW",'name', 'Tm'] + Parser.goalie_headings], left_on=['name','abbrev'], right_on=['name', 'Tm'], how='left')
        df.rename(columns={'FOW': 'FW'}, inplace=True)
        df.set_index('player_id',inplace=True)
        return df

    def parse(self):
        return self.ppool

    def _fix_yahoo_team_abbr(self, df):
        nhl_team_mappings = {'LA': 'LAK', 'Ott': 'OTT', 'Bos': 'BOS', 'SJ': 'SJS', 'Anh': 'ANA', 'Min': 'MIN',
                             'Nsh': 'NSH',
                             'Tor': 'TOR', 'StL': 'STL', 'Det': 'DET', 'Edm': 'EDM', 'Chi': 'CHI', 'TB': 'TBL',
                             'Fla': 'FLA',
                             'Dal': 'DAL', 'Van': 'VAN', 'NJ': 'NJD', 'Mon': 'MTL', 'Ari': 'ARI', 'Wpg': 'WPG',
                             'Pit': 'PIT',
                             'Was': 'WSH', 'Cls': 'CBJ', 'Col': 'COL', 'Car': 'CAR', 'Buf': 'BUF', 'Cgy': 'CGY',
                             'Phi': 'PHI'}
        df["editorial_team_abbr"].replace(nhl_team_mappings, inplace=True)


def init_prediction_builder(lg, cfg):
    return Parser(lg, "espn.skaters.proj.csv", "espn.goalies.proj.csv")

def scrape_and_parse(pick_goalies, csv_file_name):
    sc = ProjectionScraper()
    sc.scrape()
    # p = Parser()
    # df = p.parse(0)


if __name__ == "__main__":
    scrape_and_parse(False, "espn.skaters.proj.csv")
  # scrape_and_parse(True, "espn.goalies.proj.csv")
