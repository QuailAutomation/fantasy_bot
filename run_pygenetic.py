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

def produce_csh_ranking(predictions, scoring_categories, selector, ranking_column_name='fantasy_score'):
        """Create ranking by summing standard deviation of each stat, summing, then dividing by num stats."""
        f_mean = predictions.loc[selector,scoring_categories].mean()
        f_std =predictions.loc[selector,scoring_categories].std()
        f_std_performance = (predictions.loc[selector,scoring_categories] - f_mean)/f_std
        for stat in scoring_categories:
            predictions.loc[selector, stat + '_std'] = (predictions[stat] - f_mean[stat])/f_std[stat]
        predictions.loc[selector, ranking_column_name] = f_std_performance.sum(axis=1)/len(scoring_categories)
        return predictions

def print_rcs(roster_change_set, score, projected_stats):
    for rc in roster_change_set.roster_changes:
        print(f"Date: {rc.change_date}, in: {projected_stats.at[rc.in_player_id,'name']}({rc.in_player_id}), out: {projected_stats.at[rc.out_player_id,'name']}({rc.out_player_id})")
    print(f"Score: {score}\n")

def do_run():
    # celery = init_celery()
    """Run the algorithm."""
    week = 1
    # league_id = '396.l.53432'
    league_id = '403.l.41177'
    # league_id = "403.l.18782"
    league: FantasyLeague = FantasyLeague(league_id)
    team_key = league.team_key()
    my_team_id = int(team_key.split('.')[-1])
    my_team = league.team_by_key(team_key)
    # could allow override of opp here
    opponent_key = my_team.matchup(week)

    date_range = pd.date_range(*league.week_date_range(week))
    league = league.as_of(date_range[0])
    league_scoring_categories = league.scoring_categories()

    projected_stats = league.get_projections()
    # no goalies for now
    projected_stats = projected_stats[projected_stats.position_type == 'P']
    if False and league:
        # set up projections and create weighted score (fpts)
        weights_series =  pd.Series([1, .75, 1, .5, 1, .1, 1], index=league_scoring_categories)
        # rank player projections, ftps is column, higher value = better
        projected_stats['fpts'] = 0
        projected_stats['fpts'] = projected_stats.loc[projected_stats.G == projected_stats.G,weights_series.index.tolist()].mul(weights_series).sum(1)
    else:
        produce_csh_ranking(projected_stats, league_scoring_categories, 
                    projected_stats.index, ranking_column_name='fpts')

    addable_players = projected_stats[ (projected_stats.fantasy_status == 'FA') & (projected_stats.fantasy_status != my_team_id)]
    add_selector = RandomWeightedSelector(addable_players,'fpts')
    droppable_players = projected_stats[(projected_stats.fantasy_status == my_team_id) & (projected_stats.percent_owned < 93)]
    drop_selector = RandomWeightedSelector(droppable_players, 'fpts', inverse=True)
    # create score comparer
    valid_players = projected_stats[projected_stats.status != 'IR']
    league_scores = {tm['team_key']:score_team(valid_players[valid_players.fantasy_status == int(tm['team_key'].split('.')[-1])], \
                                    date_range, \
                                    league_scoring_categories)[1] 
                                for tm in league.teams()}

    score_comparer = ScoreComparer(league_scores.values(),league.scoring_categories())
    score_comparer.set_opponent(league_scores[opponent_key].sum())

    factory = RosterChangeSetFactory(projected_stats, date_range, league_scoring_categories, team_id=my_team_id, num_moves=4)
    gea = CeleryFitnessGAEngine(factory=factory,population_size=300,fitness_type=('equal',2),
                                cross_prob=0.3,mut_prob = 0.1)

    def mutate(chromosome, add_selector, drop_selector, valid_dates, projected_stats, scoring_categories):
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
        elif random_number < 35:
            # lets mutate player out
            for _ in range(50):
                player_to_remove = drop_selector.select().index.values[0]
                if not any(rc.out_player_id == player_to_remove for rc in chromosome.roster_changes):
                    with suppress(RosterException):
                        chromosome.replace(roster_change_to_mutate, roster_change_to_mutate._replace(out_player_id=player_to_remove))
                    break
        elif random_number < 95:
            # lets mutate player in
            for _ in range(50):
                plyr = add_selector.select()
                player_id = plyr.index.values[0]
                if (plyr['position_type'] == 'G').values[0] or (player_id in [rc.in_player_id for rc in chromosome.roster_changes]):
                    continue
                if not any(player_id == rc.in_player_id for rc in chromosome.roster_changes):
                    with suppress(RosterException):
                        chromosome.replace(roster_change_to_mutate, roster_change_to_mutate._replace(in_player_id=player_id, in_projections=plyr[scoring_categories + ['eligible_positions', 'team_id', 'fpts']]))
                    break
        else:
            if len(chromosome.roster_changes) > 1:
                del (chromosome.roster_changes[roster_change_to_mutate_index])

        return chromosome


    def crossover(changeset_1, changeset_2, league):
        mates = [changeset_1, changeset_2]
        if any(len(change.roster_changes) < 2 for change in mates):
            return (changeset_1, changeset_2)
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
    gea.addMutationHandler(mutate, 2, add_selector, drop_selector, date_range, projected_stats, league_scoring_categories)
    # & (projected_stats.status != "IR")
    all_players = projected_stats[(projected_stats.position_type == "P") ].loc[:,['eligible_positions', 'team_id', 'fantasy_status', 'fpts'] + league_scoring_categories]
    gea.setFitnessHandler(fitness, all_players, date_range, league_scoring_categories, score_comparer, my_team_id)
    gea.setSelectionHandler(Utils.SelectionHandlers.best)


    gea.evolve(5)
    print_rcs(*gea.best_fitness, projected_stats)
    for _ in range(20):
        try:
            gea.continue_evolve(1)
            
            print("hall of fame:")
            print_rcs(*gea.hall_of_fame, projected_stats)
        except TypeError as e:
            print(e)
    pass
    
if __name__ == "__main__":
    do_run()