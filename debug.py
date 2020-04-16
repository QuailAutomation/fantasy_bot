from csh_fantasy_bot.league import FantasyLeague

league = FantasyLeague('396.l.53432')

all = league.all_players()
print(f'num players: {all}')