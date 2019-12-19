from selenium import webdriver
from bs4 import BeautifulSoup
import time
import pandas as pd

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys

#url = 'https://hockey.fantasysports.yahoo.com/hockey/53432/players?&sort=AR&sdir=1&status=2&pos=P&stat1=S_L7&jsenabled=1/'

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

    def scrape(self, pick_goalies, num_pages):
        driver = webdriver.Chrome()
        file_names = []
        try:
            driver.maximize_window()
            driver.implicitly_wait(15)
            driver.get(self.url())
            wait = WebDriverWait(driver, 10)

            emailelem = wait.until(EC.presence_of_element_located((By.ID, 'login-username')))
            emailelem.send_keys('craig_hamilton2000@yahoo.com')

            wait.until(EC.presence_of_element_located((By.ID, 'login-signin')))
            emailelem.submit()

            wait.until(EC.element_to_be_clickable((By.ID, 'login-signin')))
            passwordelem = wait.until(EC.presence_of_element_located((By.ID, 'login-passwd')))
            passwordelem.send_keys('thunder')
            passwordelem.send_keys(Keys.RETURN)

            print('Done')


            #time.sleep(5)
            fn = "yahoo_fantasy_player_stats.html"
            with open(fn, "w") as f:
                soup = BeautifulSoup(driver.page_source, "lxml")
                f.write(soup.prettify())
                file_names.append(fn)

        finally:
            driver.close()
        return file_names

    def url(self):
        #return "https://www.fantasysp.com/projections/hockey/daily/"
        #return "https://www.fantasysp.com/projections/hockey/weekly/"
        return "https://hockey.fantasysports.yahoo.com/hockey/53432/players?&sort=AR&sdir=1&status=2&pos=P&stat1=S_L7&jsenabled=1/"


class Parser:
    def __init__(self, file_name):
        with open(file_name, "rb") as f:
            self.soup = BeautifulSoup(f, "lxml")

    def parse(self, index_offset):
        names = self.parse_name(index_offset)
        stats = ["G","A","SOG","PLUSMINUS","HIT","PIM","FOW"]

        for stat in stats:
            names["{}GAME".format(stat)] = names[stat].div(names["GAMES"])

        print(names.head(5))

        #names["GOALSGAME"]= names["G"].div(names["GAMES"])
        #names["ASSISTSGAME"] = names["A"].div(names["GAMES"])
        #names["GAME"] = names["A"].div(names["GAMES"])


        print(names.head(5))

        # proj = self.parse_projection(index_offset)
        # df = names.join(proj)
        # # Remove any players with missing projections
        # if 'G' in df:
        #     df = df[df.G != '--']
        # elif 'W' in df:
        #     df = df[df.W != '--']
        return names

    def parse_projection(self, index_offset):
        #table = self.soup.find_all('table')[3]
        table = self.soup.find("table", {"class": "table sortable table-clean table-add-margin table-fixed"})
        #tab = soup.find("table", {"class": "wikitable sortable"})

        headings = [th.get_text().strip() for th in
                    table.find_all("thead")[0].find_all("th")]
        table_body = table.find('tbody')
        df = pd.DataFrame(data=[], columns=headings)
        rows = table_body.find_all('tr')
        for i, row in enumerate(rows):
            cols = [ele.text.strip() for ele in row.find_all('td')]
            df = df.append(pd.DataFrame(data=[cols], columns=headings,
                                        index=[i + index_offset]))
        return df

    def parse_name(self, index_offset):
        table = self.soup.find("table", {"class": "table sortable table-clean table-add-margin table-fixed"})
        headings = ["Name", "Tm","Pos","G","A","SOG","PLUSMINUS","HIT","PIM","FOW","GAMES"]
        table_body = table.find('tbody')
        df = pd.DataFrame(data=[], columns=headings)
        rows = table_body.find_all('tr')
        for i, row in enumerate(rows):
            name_base = row.find_all('td')[1].text.strip().split("\n")
            #name_base = row.find_all('td')[1].find_all('span')
            name = name_base[0]
            tm = name_base[3].strip()
            pos = name_base[6].strip()

            games_base = row.find_all('td')[2].text.strip().split("\n")[0]
            for i, c in enumerate(games_base):
                if not c.isdigit():
                    break
            num_games = int(games_base[:i])
            goals = float(row.find("td", {"class": "proj-g"}).text.strip())
            assists = float(row.find("td", {"class": "proj-ast"}).text.strip())
            shots = float(row.find("td", {"class": "proj-sog"}).text.strip())
            plus_minus = float(row.find("td", {"class": "proj-plusminus"}).text.strip())
            hit = float(row.find("td", {"class": "proj-hit"}).text.strip())
            pim = float(row.find("td", {"class": "proj-pim"}).text.strip())
            fow = float(row.find("td", {"class": "proj-fow"}).text.strip())


            df = df.append(pd.DataFrame(data=[[name, tm,pos,goals,assists,shots,plus_minus,hit,pim,fow,num_games]], columns=headings,
                                        index=[i + index_offset]))
        return df


def scrape_and_parse(pick_goalies, csv_file_name):
    sc = ProjectionScraper()
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
