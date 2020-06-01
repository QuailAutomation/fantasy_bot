"""Run pygenetic GA analysis."""
import pandas as pd
import random
import copy
from contextlib import suppress

from pygenetic import GAEngine
from pygenetic import Utils

from yahoo_fantasy_api.team import Team

from csh_fantasy_bot.ga import RosterChangeSetFactory, fitness, RandomWeightedSelector, CeleryFitnessGAEngine
from csh_fantasy_bot.league import FantasyLeague
from csh_fantasy_bot.nhl import score_team
from csh_fantasy_bot.roster_change_optimizer import RosterChangeSet, RosterException
from csh_fantasy_bot.celery_app import app
from csh_fantasy_bot.scoring import ScoreComparer

def do_run():
    # celery = init_celery()
    """Run the algorithm."""
    week = 21
    league_id = '396.l.53432'
    my_team_id = 2
    league: FantasyLeague = FantasyLeague(league_id)
    team_key = league.team_key()
    my_team = league.team_by_key(team_key)
    # could allow override of opp here
    opponent_key = my_team.matchup(week)

    date_range = pd.date_range(*league.week_date_range(week))
    league = league.as_of(date_range[0])
    
    # set up projections and create weighted score (fpts)
    weights_series =  pd.Series([1, .75, 1, .5, 1, .1, 1], index=league.scoring_categories())
    projected_stats = league.get_projections()
    projected_stats['fpts'] = 0
    projected_stats['fpts'] = projected_stats.loc[projected_stats.G == projected_stats.G,weights_series.index.tolist()].mul(weights_series).sum(1)
    addable_players = projected_stats[(projected_stats.position_type == 'P') & (projected_stats.fantasy_status == 'FA')]
    add_selector = RandomWeightedSelector(addable_players,'fpts')
    drop_selector = RandomWeightedSelector(projected_stats[(projected_stats.fantasy_status == my_team_id) & (projected_stats.percent_owned < 93)], 'fpts', inverse=True)
    # create score comparer
    valid_players = projected_stats[(projected_stats.position_type == 'P') & (projected_stats.status != 'IR')]
    league_scores = {tm['team_key']:score_team(valid_players[valid_players.fantasy_status == int(tm['team_key'].split('.')[-1])], \
                                    date_range, \
                                    league.scoring_categories())[1] 
                                for tm in league.teams()}

    scoring_list = [league_scores[x] for x in league_scores.keys()]
    score_comparer = ScoreComparer(scoring_list,league.scoring_categories())
    score_comparer.set_opponent(league_scores[opponent_key].sum())

    factory = RosterChangeSetFactory(projected_stats, date_range, league.scoring_categories(), team_id=my_team_id, num_moves=4)
    gea = CeleryFitnessGAEngine(factory=factory,population_size=200,fitness_type=('equal',8),
                                cross_prob=0.7,mut_prob = 0.05)

    def mutate(chromosome, league, add_selector, drop_selector, valid_dates):
        if len(chromosome.roster_changes) == 0:
            # nothing to mutate here
            return chromosome
        # let's pick one of the roster changes to mutate
        roster_change_to_mutate_index = random.randint(1, len(chromosome.roster_changes)) - 1
        roster_change_to_mutate = chromosome.roster_changes[roster_change_to_mutate_index]
        # won't try and mutate date if there is not more than 1 valid date
        random_number = random.randint(1 if len(valid_dates) else 30, 100)
        if random_number < 30:
            # lets mutate date
            while True:
                drop_date = random.choice(valid_dates).date()
                if drop_date != roster_change_to_mutate.change_date:
                    with suppress(RosterException):
                        chromosome.replace(roster_change_to_mutate, roster_change_to_mutate._replace(change_date=drop_date))
                    break
        elif random_number < 55:
            # lets mutate player out
            for _ in range(50):
                player_to_remove = drop_selector.select().index.values[0]
                if not any(rc.out_player_id == player_to_remove for rc in chromosome.roster_changes):
                    with suppress(RosterException):
                        chromosome.replace(roster_change_to_mutate, roster_change_to_mutate._replace(out_player_id=player_to_remove))
                    break
        elif random_number < 90:
            # lets mutate player in
            for _ in range(50):
                plyr = add_selector.select()
                player_id = plyr.index.values[0]
                if (plyr['position_type'] == 'G').values[0] or (player_id in [rc.in_player_id for rc in chromosome.roster_changes]):
                    continue
                if not any(player_id == rc.in_player_id for rc in chromosome.roster_changes):
                    with suppress(RosterException):
                        chromosome.replace(roster_change_to_mutate, roster_change_to_mutate._replace(in_player_id=player_id))
                    break
        else:
            if len(chromosome.roster_changes) > 1:
                del (chromosome.roster_changes[roster_change_to_mutate_index])

        return chromosome


    def crossover(changeset_1, changeset_2, league):
        mates = [changeset_1, changeset_2]
        changes_to_remove = None
        num_roster_changes_to_remove = 0
        # let's remove second 1/2 of roster changes in first parent.  will add those to other parent.
        if len(mates[0]) > 1:
            num_roster_changes_to_remove = 1
            changes_to_remove = random.choice(mates[0])
        changes_to_remove_2 = None
        num_roster_changes_to_remove_2 = 0
        if len(mates[1]) > 1:
            num_roster_changes_to_remove_2 = 1
            changes_to_remove_2 = random.choice(mates[1])

        offspring = []
        offspring1 = copy.copy(mates[0])
        if changes_to_remove is not None or changes_to_remove_2 is not None:
            try:
                offspring1.replace(changes_to_remove, changes_to_remove_2)
                if len(offspring1) == 0:
                    offspring1 = mates[0]
                else:
                    offspring1.score = None
            except RosterException as e:
                offspring1 = mates[0]
            offspring.append(offspring1)
            offspring2 = copy.copy(mates[1])
            try:
                offspring2.replace(changes_to_remove_2, changes_to_remove)
                if len(offspring2) == 0:
                    offspring2 = mates[1]   
                else:
                    offspring2.score = None
            except RosterException as e:
                offspring2 = mates[1]
            offspring.append(offspring2)
        else:
            offspring = [mates[0], mates[1]]
        return offspring[0], offspring[1]


    gea.addCrossoverHandler(crossover,1,league)
    gea.addMutationHandler(mutate,2, league, add_selector, drop_selector, date_range)
    all_players = projected_stats[(projected_stats.position_type == "P") & (projected_stats.status != "IR")].loc[:,['eligible_positions', 'team_id', 'fantasy_status'] + league.scoring_categories()]
    gea.setFitnessHandler(fitness, all_players, date_range, league.scoring_categories(), score_comparer, my_team_id)
    gea.setSelectionHandler(Utils.SelectionHandlers.best)
    try:
        gea.evolve(10)
    except TypeError as e:
        print(e)
    pass

if __name__ == "__main__":
    do_run()