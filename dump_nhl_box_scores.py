import datetime
import json
import os

import pymongo
from jsonpath_ng import jsonpath, parse

DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'

directory = 'box-scores'

myclient = pymongo.MongoClient("mongodb://192.168.1.220:27017/")

mydb = myclient.fantasy
box_scores = mydb.box_scores


for filename in os.listdir(directory):
    f = os.path.join(directory, filename)
    # checking if it is a file
    if os.path.isfile(f) and '.json' in filename:
        print(f)

        with open(f, 'r', encoding='utf-8') as game_json:
            json_data=json.loads(game_json.read())


        cleaned_game_data = {}
        cleaned_game_data['_id'] = filename.strip('.json')
        cleaned_game_data['game_date'] = datetime.datetime.strptime(json_data['game_date'], DATETIME_FORMAT)

        for team in ['away', 'home']:
            team_info = json_data['teams'][team]
            team_stats = team_info['teamStats']
            cleaned_game_data[team] = {}
            cleaned_game_data[team]['id'] = team_info['team']['id']
            cleaned_game_data[team]['name'] = team_info['team']['name']
            cleaned_game_data[team]['teamStats'] = team_stats 
            cleaned_game_data[team]['players'] = []
            for player in team_info['players'].values():
                player_info = {}
                player_info['position'] = player['person']['primaryPosition']['abbreviation']
                player_info['name'] = player['person']['fullName']
                # player_info['age'] = player['person']['currentAge']
                player_info['id'] = str(player['person']['id'])
                if 'skaterStats' in player['stats'].keys():
                    player_info['stats'] = player['stats']['skaterStats']
                    cleaned_game_data[team]['players'].append(player_info)
                
        print(myclient.list_database_names())


        box_scores.insert_one(cleaned_game_data)            

# es.index(index='nhl-boxscore-2022', doc_type='doc', body=cleaned_game_data)

# print(len(data))
