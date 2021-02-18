"""Run pygenetic GA analysis."""
import pandas as pd
import random
import copy
import datetime
from contextlib import suppress

from pygenetic import GAEngine
from pygenetic import Utils

from csh_fantasy_bot.ga import RosterChangeSetFactory, fitness, RandomWeightedSelector, CeleryFitnessGAEngine
from csh_fantasy_bot.bot import ManagerBot
from csh_fantasy_bot.league import FantasyLeague
from csh_fantasy_bot.roster_change_optimizer import RosterException
from csh_fantasy_bot.celery_app import app

def do_run(week=5, league_id='403.l.41177', population_size=50):
    """Run the algorithm."""
    week = 5
    league_id = '403.l.41177'
    # league_id = "403.l.18782"
    
    manager: ManagerBot = ManagerBot(week=week, simulation_mode=False,league_id=league_id)

    league: FantasyLeague = manager.lg
    team_key = league.team_key()
    my_team_id = int(team_key.split('.')[-1])
    my_team = league.team_by_key(team_key)

    date_range = pd.date_range(*league.week_date_range(week))
    league = league.as_of(date_range[0])
    league_scoring_categories = league.scoring_categories()

    projected_stats = manager.all_player_predictions

    addable_players = projected_stats[ (projected_stats.fantasy_status == 'FA') & (projected_stats.fantasy_status != my_team_id)]
    add_selector = RandomWeightedSelector(addable_players,'fpts')
    droppable_players = projected_stats[(projected_stats.fantasy_status == my_team_id) & (projected_stats.percent_owned < 92) & (projected_stats.fpts < 1)]
    drop_selector = RandomWeightedSelector(droppable_players, 'fpts', inverse=True)
    
    # valid dates are next day we can make changes for to end of fantasy week
    first_add = datetime.datetime.strptime(league.settings()['edit_key'], "%Y-%m-%d")
    # TODO hack because we don't handle dates correctly yet
    if league_id == "403.l.18782":
        first_add += datetime.timedelta(days=1)
    # can't be before start of week
    if first_add < date_range[0]:
        first_add = date_range[0]

    valid_roster_change_dates = pd.date_range(first_add,date_range[-1])
    num_allowed_player_adds = int(league.settings()['max_weekly_adds']) - league.num_moves_made(week=week)
    if num_allowed_player_adds == 0:
        print("No roster changes left, no need to run.")
        return
    factory = RosterChangeSetFactory(projected_stats[manager.stat_categories + ['eligible_positions', 'team_id', 'fpts']], valid_roster_change_dates, num_moves=num_allowed_player_adds, add_selector=add_selector, drop_selector=drop_selector)
    gea = CeleryFitnessGAEngine(factory=factory,population_size=population_size,
                                cross_prob=0.5,mut_prob = 0.1)

    def mutate(chromosome, add_selector, drop_selector, date_range, scoring_categories):
        if len(chromosome.roster_changes) == 0:
            # nothing to mutate here
            return chromosome
        # let's pick one of the roster changes to mutate
        roster_change_to_mutate_index = random.randint(1, len(chromosome.roster_changes)) - 1
        roster_change_to_mutate = chromosome.roster_changes[roster_change_to_mutate_index]
        RANGE_EXCLUDES_DATES = 50
        # won't try and mutate date if there is not more than 1 valid date
        random_number = random.randint(1 if len(date_range) > 1 else RANGE_EXCLUDES_DATES, 100)
        if random_number < 40:
            # lets mutate date
            while True:
                drop_date = random.choice(date_range).date()
                if drop_date != roster_change_to_mutate.change_date:
                    with suppress(RosterException):
                        chromosome.replace(roster_change_to_mutate, roster_change_to_mutate._replace(change_date=drop_date))
                    break
        elif random_number < RANGE_EXCLUDES_DATES:
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
    gea.addMutationHandler(mutate, 2, add_selector, drop_selector, valid_roster_change_dates, league_scoring_categories)
    # & (projected_stats.status != "IR")
    all_players = projected_stats[(projected_stats.position_type == "P") ].loc[:,['eligible_positions', 'team_id', 'fantasy_status', 'fpts'] + league_scoring_categories]
    gea.setFitnessHandler(fitness, all_players, date_range, league_scoring_categories, manager.score_comparer, team_key, manager.opponent.scores()[league_scoring_categories].sum().to_dict())
    gea.setSelectionHandler(Utils.SelectionHandlers.best)


    gea.evolve(5)
    rcs, score = gea.best_fitness
    rcs.pretty_print(score,projected_stats)
    for _ in range(20):
        gea.continue_evolve(1)
        print("hall of fame:")
        rcs, score = gea.best_fitness
        rcs.pretty_print(score,projected_stats)
        print(manager.score_comparer.score(manager.score_team(roster_change_set=rcs)[1]))

    
if __name__ == "__main__":
    do_run()