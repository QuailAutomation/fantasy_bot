from selenium import webdriver
from bs4 import BeautifulSoup
import time
import pandas as pd
from nhl_scraper.nhl import Scraper

#url = 'https://www.fantasysp.com/projections/hockey/daily/'

#!/usr/bin/python

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


class ProjectionScraper:
    def __init__(self):
        pass

    def scrape(self):
        driver = webdriver.Chrome()
        driver.maximize_window()
        positions_to_scrape = ['C','LW','RW','D']
        file_names = []
        url = "https://www.fantasysp.com/projections/hockey/weekly/{}"
        try:
            for position_scraped in positions_to_scrape:

                driver.implicitly_wait(15)
                driver.get(url.format(position_scraped))

                time.sleep(5)
                fn = "fantasysp_weekly-{}.html"
                with open(fn.format(position_scraped), "w") as f:
                    soup = BeautifulSoup(driver.page_source, "lxml")
                    f.write(soup.prettify())
                    file_names.append(fn.format(position_scraped))

        finally:
            driver.close()

        return file_names


class Parser:

    def __init__(self):
        # which positions to scrape from fantasysp
        self.positions = ['C','LW','RW','D']
        headings = ["Name", "Tm", "Pos", "G", "A", "SOG", "+/-", "HIT", "PIM", "FOW", "GAMES"]
        df = pd.DataFrame(data=[], columns=headings)
        index_offset = 0
        for position in self.positions:
            print("Processing: {}".format(position))
            file_name = "fantasysp_weekly-{}.html".format(position)

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
                    goals = float(row.find("td", {"class": "proj-g"}).text.strip()) / num_games
                    assists = float(row.find("td", {"class": "proj-ast"}).text.strip()) / num_games
                    shots = float(row.find("td", {"class": "proj-sog"}).text.strip()) / num_games
                    plus_minus = float(row.find("td", {"class": "proj-plusminus"}).text.strip()) / num_games
                    hit = float(row.find("td", {"class": "proj-hit"}).text.strip()) / num_games
                    pim = float(row.find("td", {"class": "proj-pim"}).text.strip()) / num_games
                    fow = float(row.find("td", {"class": "proj-fow"}).text.strip()) / num_games

                    df = df.append(pd.DataFrame(
                        data=[[name, tm, pos, goals, assists, shots, plus_minus, hit, pim, fow, num_games]],
                        columns=headings, index=[i + index_offset]))
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
        # my_roster = pd.DataFrame(roster_cont.get_roster())
        # df = my_roster.merge(self.ppool, left_on='name',right_on='name', how="left")

        if 'team_id' not in my_roster.columns:
            # we must map in teams
            self._fix_yahoo_team_abbr(my_roster)
            self.nhl_scraper = Scraper()

            nhl_teams = self.nhl_scraper.teams()
            nhl_teams.set_index("id")
            nhl_teams.rename(columns={'name': 'team_name'}, inplace=True)

            my_roster = my_roster.merge(nhl_teams, left_on='editorial_team_abbr', right_on='abbrev')
            my_roster.rename(columns={'id': 'team_id'}, inplace=True)



        stats = ["G", "A", "SOG", "+/-", "HIT", "PIM", "FOW"]
        df = pd.merge(my_roster, self.ppool[["G", "A", "SOG", "+/-", "HIT", "PIM", "FOW",'name']], on='name', how='left')

        try:
            df.rename(columns={'team_id_x': 'team_id'}, inplace=True)
        except KeyError:
            pass

        # Then we'll figure out the number of games each player is playing
        # this week.  To do this, we'll verify the team each player players
        # for then using the game count added as a column.
        # team_ids = []
        # wk_g = []
        # for plyr_series in df.iterrows():
        #     plyr = plyr_series[1]
        #     (team_id, g) = self._find_players_schedule(plyr['name'])
        #     team_ids.append(team_id)
        #     wk_g.append(g)
        # df['team_id'] = team_ids
        # df['WK_G'] = wk_g

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

    def _get_yahoo_predicted_stats(self, players):
        # if there are stats missing, let's load player stats from yahoo


        # let's double check for players on roster who don't have current projections.  We will create our own by using this season's stats
        ids_no_stats = list(
            players.query('G != G & position_type == "P" & status != "IR"').player_id.values)
        the_stats = self.lg.player_stats(ids_no_stats, 'season')
        stats_to_track = ["G", "A", "SOG", "+/-", "HIT", "PIM", "FOW"]
        for player_w_stats in the_stats:
            # a_player = players[players.player_id == player_w_stats['player_id']]
            for stat in stats_to_track:
                if player_w_stats['GP'] > 0:
                    #  hack for now because yahoo returns FW but rest of code uses FOW
                    if stat != 'FOW':
                        # a_player[stat] = player_w_stats[stat] / player_w_stats['GP']
                        players.loc[players['player_id'] == player_w_stats['player_id'], [stat]] = player_w_stats[
                                                                                                       stat] / \
                                                                                                   player_w_stats['GP']
                    else:
                        players.loc[players['player_id'] == player_w_stats['player_id'], [stat]] = player_w_stats[
                                                                                                       'FW'] / \
                                                                                                   player_w_stats['GP']
        return players



def init_prediction_builder(lg, cfg):
    return Parser(lg, "espn.skaters.proj.csv", "espn.goalies.proj.csv")

def scrape_and_parse(pick_goalies, csv_file_name):
    sc = ProjectionScraper()
    sc.scrape()
    #file_names = sc.scrape(pick_goalies, 3 if pick_goalies else 5)
    file_names= ['fantasysp_weekly.html']
    df = None
    for fn in file_names:
        p = Parser(fn)
        if df is None:
            df = p.parse(0)
        else:
            df = df.append(p.parse(len(df.index)))
#    df.to_csv(csv_file_name)


if __name__ == "__main__":
    scrape_and_parse(False, "espn.skaters.proj.csv")
  # scrape_and_parse(True, "espn.goalies.proj.csv")
