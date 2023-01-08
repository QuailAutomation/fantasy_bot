import numpy as np
import pandas as pd
import pymongo

pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

scoring_categories = ['G','A','+/-', 'PPP', 'SOG', 'HIT']
#define function to calculate cv
cv = lambda x: np.std(x, ddof=1) / np.mean(x) * 100 

myclient = pymongo.MongoClient("mongodb://192.168.1.220:27017/")
mydb = myclient.fantasy

pipeline = [
    # {
    #     '$match': {
    #         '_id': '2022010101'
    #     }
    # }, 
    {
        '$addFields': {
            'away.players.team_id': '$away.id', 
            'away.players.opponent': '$home.name', 
            'away.players.opponent_id': '$home.id', 
            'away.players.home_away': 'away'
        }
    }, {
        '$addFields': {
            'home.players.team_id': '$home.id', 
            'home.players.opponent': '$away.name', 
            'home.players.opponent_id': '$away.id', 
            'home.players.home_away': 'home'
        }
    }, {
        '$project': {
            'game_date': 1, 
            'players': {
                '$concatArrays': [
                    '$away.players', '$home.players'
                ]
            }
        }
    }, {
        '$unwind': {
            'path': '$players', 
            'preserveNullAndEmptyArrays': True
        }
    }, {
        '$project': {
            'game_date': 1, 
            'player_id': '$players.id', 
            'player_name': '$players.name', 
            'home_away': '$players.home_away', 
            'opponent_name': '$players.opponent', 
            'opponent_id': '$players.opponent_id', 
            'team_id': '$players.team_id', 
            'position': '$players.position', 
            'toi': '$players.stats.timeOnIce', 
            'A': '$players.stats.assists', 
            'G': '$players.stats.goals', 
            'SOG': '$players.stats.shots', 
            'HIT': '$players.stats.hits', 
            'PPG': '$players.stats.powerPlayGoals', 
            'PPA': '$players.stats.powerPlayAssists', 
            'PPP': {
                '$sum': [
                    '$players.stats.powerPlayGoals', '$players.stats.powerPlayAssists'
                ]
            },
            'PIM': '$players.stats.penaltyMinutes', 
            '+/-': '$players.stats.plusMinus', 
            'e_toi': '$players.stats.evenTimeOnIce', 
            'pp_toi': '$players.stats.powerPlayTimeOnIce'
        }
    }
]


query_result = mydb.box_scores.aggregate(pipeline)
query_result = list(query_result)
# df = pd.io.json.json_normalize(query_result)

# box_scores = mydb.box_scores.find()

box_score_df = pd.DataFrame(list(query_result))
pass
