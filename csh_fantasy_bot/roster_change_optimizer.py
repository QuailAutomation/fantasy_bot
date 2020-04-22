#!/bin/python

import timeit
from copy import copy, deepcopy
import logging
import datetime
import numpy as np
import pandas as pd
from progressbar import ProgressBar, Percentage, Bar
import math
import random
from csh_fantasy_bot import roster
from yahoo_fantasy_api import Team
from csh_fantasy_bot.nhl import BestRankedPlayerScorer

import cProfile, pstats, io

max_lineups = 100
generations = 20
ELITE_NUM = int(5)


def profile(fnc):
    """Decorator that uses cProfile to profile a function."""

    def inner(*args, **kwargs):
        pr = cProfile.Profile()
        pr.enable()
        retval = fnc(*args, **kwargs)
        pr.disable()
        s = io.StringIO()
        sortby = 'cumulative'
        ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
        ps.print_stats()


def optimize_with_genetic_algorithm(score_comparer,
                                    avail_plyrs, locked_plyrs, league, week):
    """
    Loader for the GeneticAlgorithm class.

    See GeneticAlgorithm.__init__ for parameter type descriptions.
    """
    algo = GeneticAlgorithm(score_comparer, avail_plyrs,
                            locked_plyrs, league, week)
    return algo.run(generations)


class GeneticAlgorithm:
    """
    Optimize the lineup using a genetic algorithm.

    The traits of the algorithm and how it relates to lineup building is
    as follows:
    - chromosomes: lineups
    - genes: players in the lineup
    - population (group): random set of lineups that use all available players
    - fitness function: evaluation a lineup against the base line with the
    score_comparer

    When apply generations to the chromosomes, the following applies:
    - selection: Lineups that have the best score are more likely to be
    selected.
    - crossover: Involves merging of two lineups.
    - mutate: Randomly swapping out a player with someone else

    :param cfg: Loaded config object
    :type cfg: configparser.ConfigParser
    :param score_comparer: Object that is used to compare two lineups to
    determine the better one
    :type score_comparer: bot.ScoreComparer
    
    :param avail_plyrs: Pool of available players that can be included in
    a lineup
    :type avail_plyrs: DataFrame
    :param locked_plyrs: Players that must exist in the optimized lineup
    :type locked_plyrs: list
    :return: If a better lineup was found, this will return it.  If no better
    lineup was found this returns None
    :rtype: list or None
    """

    def __init__(self, score_comparer, avail_plyrs,
                 locked_plyrs, league, week):
        # self.cfg = cfg
        self.log = logging.getLogger(__name__)
        self.score_comparer = score_comparer
        self.ppool = avail_plyrs
        self.population = []
        self.locked_ids = [e["player_id"] for e in locked_plyrs]
        self.oppenents_estimates = score_comparer.opp_sum
        self.league = league
        # TODO this should be loaded from league
        self.player_stats = ["G", "A", "+/-", "PIM", "SOG", "FW", "HIT"]
        start_date, end_date = self.league.week_date_range(week)
        self.date_range = pd.date_range(start_date, end_date)
        # need what dates we can still do things when running during the week
        first_change_date = self.league.edit_date()
        if self.date_range[0] > first_change_date or first_change_date > self.date_range[-1]:
            first_change_date = self.date_range[0]
        self.my_team: Team = self.league.to_team(self.league.team_key())
        self.date_range_for_changes = pd.date_range(first_change_date, self.date_range[-1])
        self.waivers = self.league.waivers()
        self.droppable_players = self._generate_droppable_players()
        self.team_full_roster = self.league.to_team(self.league.team_key()).roster(day=self.league.edit_date())

        self.my_scorer: BestRankedPlayerScorer = BestRankedPlayerScorer(self.league, self.my_team,
                                                                        self.ppool, self.date_range)
    def _check_elite_hasnt_regressed(self, last_elite_score):
        try:
            if self.population[ELITE_NUM - 1].score < last_elite_score:
                self.log.exception("Reduced elite score.")
            else:
                last_elite_score = self.population[ELITE_NUM - 1].score
        except TypeError as e:
            self.log.exception(e)

    def run(self, generations):
        """
        Optimize a lineup by running the genetic algorithm.

        :param generations: The number of generations to run the algorithm for
        :type generations: int
        :return: The best lineup we generated.  Or None if no lineup was
        generated
        :rtype: list or None
        """

        self._init_progress_bar(generations)
        self._init_population()
        try:
            self.population = sorted(self.population, key=lambda e: e.score, reverse=True)
        except ValueError as e:
            self.log.exception(e)
        if len(self.population) == 0:
            return None
        last_elite_score = self.population[ELITE_NUM - 1].score
        for generation in range(generations):
            if generation % 2 == 0:
                best = self.population[0]
                print("Best as of: {}, pop len: {}".format(generation, len(self.population)))
                print('player_out, player_in, change_date')
                self._print_roster_change_set(best)
                print(self.my_scorer.score(best).sum().to_dict())
                # print("Summary:\n{}".format(best.scoring_summary.head(20)))
            self._update_progress(generation)
            self._check_elite_hasnt_regressed(last_elite_score)
            print('pop len pre mate: {}'.format(len(self.population)))
            self._mate()
            print('pop len post mate: {}'.format(len(self.population)))
            self._check_elite_hasnt_regressed(last_elite_score)
            self._mutate()
            print('pop len post mutate: {}'.format(len(self.population)))
            unscored = [rc for rc in self.population if rc.score is None]
            print('Unscored: {}'.format(len(unscored)))
            self._set_scores(unscored)

            self.population = sorted(self.population, key=lambda e: e.score, reverse=True)
            self._check_elite_hasnt_regressed(last_elite_score)

            last_elite_score = self.population[ELITE_NUM - 1].score
        self.log.info(
            "Ended with population size of {}".format(len(self.population)))
        return self.population[0]

    def _print_roster_change_set(self, roster_changes):
        print("Suggestions for roster changes")
        print("Score: {}".format(roster_changes.score))
        for row in roster_changes.roster_changes:
            try:
                player_out_name = self.ppool.loc[row['player_out'], 'name']
                player_in_name = self.ppool.loc[row['player_in'], 'name']
                roster_move_date = row['change_date']
                print("Date: {} - Drop: {} ({})- Add: {} ({})".format(roster_move_date, player_out_name,
                                                                      row['player_out'], player_in_name,
                                                                      row['player_in']))
                # print("roster_changes.append([{}, {}, np.datetime64('{}')])".format(row['player_out'], row['player_in'],
                #                                                                     roster_move_date))

            except IndexError as e:
                self.log.exception(e)
                print("Id out out player was: {}".format(row['player_out']))

    def _generate_droppable_players(self):
        waivers_ids = [e["player_id"] for e in self.waivers] + self.locked_ids
        droppable_players = []
        for plyer in self.my_team.roster():
            if plyer['player_id'] not in waivers_ids and plyer['position_type'] != 'G':
                droppable_players.append(plyer['player_id'])
        return droppable_players

    def _init_progress_bar(self, generations):
        """
        Initialize the progress bar

        :param generations: Number of generations we will do
        """
        self.pbar = ProgressBar(widgets=[Percentage(), Bar()],
                                maxval=generations)
        self.pbar.start()

    def _update_progress(self, generation):
        """
        Shows progress of the lineup selection.

        :param generation: Current generation number
        :param generations: Max number of generations
        """
        self.pbar.update(generation + 1)

    def _init_population(self):
        self.population = []
        self.last_mutated_roster_change = None
        #TODO this is a hard code, manager should be setting
        # TODO get this to work for zero
        changes_allowed = 4
        # selector = self._gen_player_selector(gen_type='pct_own')
        selector = self._gen_player_selector(gen_type='fpts')
        self._generate_roster_change_sets(selector, max_lineups, roster_changes_allowed=changes_allowed)

        selector = self._gen_player_selector(gen_type='random')
        for _ in range(max_lineups * 2):
            if len(self.population) >= max_lineups:
                break
            self._generate_roster_change_sets(selector, max_lineups, roster_changes_allowed=changes_allowed)

    
    def _gen_player_selector(self, gen_type='pct_own'):
        """
        Generate a player selector for a given generation type

        :param gen_type: Specify how to sort the player selector.  Acceptable
            values are 'pct_own' and 'random'.  'pct_own' will pick lineups
            with preference to the players who have the highest percent owned.
            'random' will generate totally random lineups.
        :return: built PlayerSelector
        """
        selector = roster.PlayerSelector(self.ppool.copy().reset_index())
        if gen_type == 'pct_own':
            selector.set_descending_categories([])
            selector.rank(['percent_owned'])
        elif gen_type =='fpts':
            player_stats = ["G", "A", "+/-", "PIM", "SOG", "FW", "HIT"]
            weights_series = pd.Series([1, 1, .5, .5, .5, .3, .5], index=player_stats)
            selector.ppool['fpts'] = selector.ppool[player_stats].mul(weights_series).sum(1)

            selector.set_descending_categories([])
            selector.rank(['fpts'])
        else:
            assert (gen_type == 'random')
            selector.shuffle()
        return selector

    
    def _fit_plyr_to_change_set(self, plyer, change_set):
        fit = True
        for change in change_set:
            if change.player_in == plyer:
                fit = False
                break
        return fit

    def _generate_roster_change_sets(self, selector, max_roster_change_sets, roster_changes_allowed):
        # how many roster changes have been made so far
        # when is next date we can make roster changes for ?
        # adjust date range so doesn't try for roster changes earlier in week
        assert (len(self.population) < max_roster_change_sets)
        team_roster = pd.DataFrame(self.team_full_roster)
        roster_change_sets = self.population
        # always start with no roster changes
        roster_change_sets.append(RosterChangeSet(max_allowed=roster_changes_allowed))
        last_roster_change_set: RosterChangeSet = RosterChangeSet(max_allowed=roster_changes_allowed)
        number_roster_changes_to_place = random.randint(1, roster_changes_allowed)
        for plyr in selector.select():
            fit = False
            if len(self.population) == max_roster_change_sets:
                break

            if plyr['player_id'] in team_roster.player_id.values or plyr['position_type'] == 'G' or plyr[
                'status'] == 'IR':
                continue
            try:
                drop_date = random.choice(self.date_range_for_changes).date()
            except IndexError as e:
                self.log.exception(e)

            if len(last_roster_change_set.roster_changes) == number_roster_changes_to_place:
                if last_roster_change_set not in self.population:
                    roster_change_sets.append(last_roster_change_set)
                last_roster_change_set = RosterChangeSet(max_allowed=roster_changes_allowed)
                number_roster_changes_to_place = random.randint(1, roster_changes_allowed)

            while len(last_roster_change_set.roster_changes) < number_roster_changes_to_place:
                # let's pick someone to remove
                while True:
                    player_to_remove = random.choice(self.droppable_players)
                    try:
                        valid_positions = self.ppool.at[player_to_remove, 'position_type']
                        if valid_positions is not None and 'G' not in valid_positions:
                            break
                    except KeyError as e:
                        self.log.exception(e)
                if last_roster_change_set.can_drop_player(player_to_remove):
                    # create a roster change
                    try:
                        last_roster_change_set.add(player_to_remove, plyr['player_id'], drop_date)
                    except Exception as e:
                        self.log.exception(e)
                break

        # start_week, end_week = self.league.week_date_range(self.league.current_week())

        # score each of the change sets
        for index, change_set in enumerate(roster_change_sets):
            if change_set.score is None:
                self._set_scores([change_set])
                if index % 19 == 0:
                    print("scored: {}, ({})".format(index, change_set.score))
            # opp_sum = my_scorer.score()

    def _remove_from_pop(self, lineup):
        for i, p in enumerate(self.population):
            if lineup == p:
                if i > 5:
                    del (self.population[i])
                return
        raise RuntimeError(
            "Could not find lineup in population " + str(lineup['id']))

    def _compute_best_lineup(self):
        """
        Goes through all of the possible lineups and figures out the best

        :return: The best lineup
        """
        best_lineup = self.population[0]
        # for lineup in self.population[1:]:
        #     assert (lineup.score is not None)
        #     if lineup.score > best_lineup.score:
        #         best_lineup = lineup
        return best_lineup

    def _mate(self):
        """
        Merge two lineups to produce children that character genes from both

        The selection process regarding who to mate is determined using the
        selectionStyle config parameter.
        """
        new_pop = self.population[:ELITE_NUM]
        attempt = 0
        print("Start mating, population is: {}".format(len(self.population)))
        while len(new_pop) < len(self.population) and attempt < len(self.population) * 2:
            attempt += 1
            mates = self._pick_lineups()
            if mates:
                if mates[0] == mates[1]:
                    pass
                offspring = self._produce_offspring(mates)
                if len(offspring) < 2:
                    pass
                new_pop = new_pop + offspring
        if len(new_pop) < max_lineups:
            print("population has shrunk")

        self.population = new_pop

    def _pick_lineups(self):
        """
        Pick two lineups at random

        This uses the tournament selection process where random set of lineups
        are selected, then go through a tournament to pick the top number.

        :return: List of lineups.  Return None if not enough lineups exists.
        """
        k = int(4)
        if k > len(self.population) - ELITE_NUM:
            pw = math.floor(math.log(len(self.population), 2))
            k = 2 ** pw
        assert (math.log(k, 2).is_integer()), "Must be a power of 2"
        participants = random.sample(self.population[ELITE_NUM + 1:], k=k)
        original_participants = participants.copy()
        if len(participants) == 1:
            return None

        rounds = math.log(k, 2) - 1
        for _ in range(int(rounds)):
            next_participants = []
            for opp_1, opp_2 in zip(participants[0::2], participants[1::2]):
                try:
                    assert (opp_1.score is not None)
                    assert (opp_2.score is not None)
                except AttributeError as e:
                    pass
                if opp_1.score > opp_2.score:
                    next_participants.append(opp_1)
                else:
                    next_participants.append(opp_2)
            participants = next_participants
        assert (len(participants) == 2)
        if participants[0] == participants[1]:
            self.log.warning("_pick_lineups is returning the same participants")
            return None
        return participants

    def _produce_offspring(self, mates):
        """
        Merge two roster change sets together to produce a set of children.

        :param mates: Two parent roster change sets that we use to produce offspring
        :return: List of lineups
        """
        assert (len(mates) == 2)
        assert (mates[0] != mates[1])
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
        offspring1 = copy(mates[0])
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
            offspring2 = copy(mates[1])
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
        return offspring[0:2]

    def _set_scores(self, roster_change_sets):
        for change_set in roster_change_sets:
            the_score = self.my_scorer.score(change_set)
            change_set.scoring_summary = the_score
            change_set.score = self.score_comparer.compute_score(the_score)

    def _mutate_roster_change(self, roster_change_set, selector, team_roster):
        rc_index = ['player_out', 'player_in', 'change_date']
        try:
            roster_change_to_mutate_index = random.randint(1, len(roster_change_set)) - 1

            roster_change_to_mutate = roster_change_set[roster_change_to_mutate_index]
            # lets mutate this change set
            random_number = random.randint(1, 100)
            if len(self.date_range_for_changes) > 1 and random_number < 30:
                # lets mutate date
                while True:
                    drop_date = random.choice(self.date_range_for_changes).date()

                    if drop_date != roster_change_to_mutate['change_date']:

                        mutated_roster_change = roster_change_to_mutate.copy()
                        mutated_roster_change['change_date'] = drop_date
                        try:
                            roster_change_set.replace(roster_change_to_mutate, mutated_roster_change)
                        except RosterException as e:
                            # this is ok, player must already exist in another change
                            pass
                        # print('mutated date')
                        break
            elif random_number < 40:
                # lets mutate player out
                for _ in range(50):
                    player_to_remove = random.choice(self.droppable_players)
                    if not any(rc['player_out'] == player_to_remove for rc in roster_change_set):
                        mutated_roster_change = roster_change_to_mutate.copy()
                        mutated_roster_change['player_out'] = player_to_remove
                        try:
                            roster_change_set.replace(roster_change_to_mutate, mutated_roster_change)
                        except RosterException as e:
                            pass

                        break
            elif random_number < 95:
                # lets mutate player in
                selector.shuffle()
                for plyr in selector.select():
                    if plyr['player_id'] in team_roster.player_id.values or plyr['position_type'] == 'G' or plyr[
                        'player_id'] in [rc['player_in'] for rc in roster_change_set.roster_changes]:
                        continue
                    if not any(plyr.player_id == rc['player_in'] for rc in roster_change_set):
                        mutated_roster_change = roster_change_to_mutate.copy()
                        mutated_roster_change['player_in'] = plyr['player_id']
                        try:
                            roster_change_set.replace(roster_change_to_mutate, mutated_roster_change)
                        except RosterException as e:
                            self.log.exception(e)
                        break
            else:
                # remove a roster change - don't have to worry about zero roster changes, eliminated 0 ones already
                if len(roster_change_set) > 1:
                    del (roster_change_set[roster_change_to_mutate_index])

            #TODO might want to defer scoring, i think it would get done later, and could be batched
            self._set_scores([roster_change_set])
        except ValueError as e:
            self.log.exception(e)
            

    def _mutate_elites(self, selector, team_roster):
        """Mutate each of the elites.  If score increases, swap mutated in."""
        for index, elite in enumerate(self.population[:ELITE_NUM]):
            if len(elite.roster_changes):
                rc = deepcopy(elite)
                self._mutate_roster_change(rc, selector, team_roster)
                try:
                    if rc.score > elite.score:
                        print('swap mutated')
                        self.population[index] = rc
                except TypeError as e:
                    self.log.exception(e)

    def _mutate(self):
        """
        Go through all of the players and mutate a certain percent.
        Mutation simply means swapping out the player with a random player.
        """
        mutate_pct = 5
        selector = self._gen_player_selector(gen_type='random')
        team_roster = pd.DataFrame(self.team_full_roster)

        self._mutate_elites(selector, team_roster)

        to_mutate = random.sample(self.population[ELITE_NUM + 1:],
                                  int((len(self.population) - (ELITE_NUM + 1)) * mutate_pct / 100))
        for rc in to_mutate:
            if len(rc) > 0:
                self._mutate_roster_change(rc, selector, team_roster)
            if rc.score is None:
                print('Scoring(mutate)')
                self._set_scores([rc])
        # for index, lineup in enumerate(self.population):
        #
        #     # lets not mutate the top 2, and only sets with atleast 1 roster change
        #     if index < ELITE_NUM or len(lineup) == 0:
        #         continue
        #
        #     if random.randint(1, 100) <= mutate_pct:
        #         self._mutate_roster_change(lineup, selector, team_roster)
        #     if lineup.score is None:
        #         self._set_scores([lineup])
        #         # TODO we should check if this roster set now equals another
        #         # for i, pop in enumerate(self.population):
        #         #     if pop == lineup and i != index:
        #         #         # this change set is now a duplicate of another, so remove from population
        #         #         del(self.population[index])


class RosterChangeSet:
    def __init__(self, changes=None, max_allowed=4):
        self.max_allowed_changes = max_allowed
        self._equality_value = None
        self.score = None
        self.roster_changes = []
        if changes is not None:
            for change in changes:
                self.add(change['player_out'], change['player_in'], change['change_date'])

    @property
    def equality_value(self):
        if self._equality_value is None:
            self._compute_equality_score()
        return self._equality_value

    def __copy__(self):
        newone = type(self)()
        newone.__dict__.update(self.__dict__)
        return newone

    def __deepcopy__(self, memodict={}):
        cloned_roster_changes = self.roster_changes.copy()

        return RosterChangeSet(cloned_roster_changes)
        # new_rc_set = RosterChangeSet()

    def __getitem__(self, i):
        try:
            return self.roster_changes[i]
        except TypeError:
            pass

    def __len__(self):
        return len(self.roster_changes)

    def _compute_equality_score(self):
        sorted_changes = sorted(self.roster_changes, key = lambda i: i['player_in'],reverse=True)
        self._equality_value = "RC" + ''.join([i["equality_score"] for i in self.roster_changes])

    def __eq__(self, other):
        if isinstance(other, RosterChangeSet):
            return self.equality_value == other.equality_value
        else:
            return False

    def __delitem__(self, key):
        del self.roster_changes[key]
        self._equality_value = None

    def can_drop_player(self, drop_player):
        """Check if player already being dropped in another roster change."""
        return drop_player not in [change['player_out'] for change in self.roster_changes]

    def add(self, player_out, player_in, change_date):
        """Add a roster change to the set."""
        if len(self.roster_changes) >= self.max_allowed_changes:
            raise RosterException("Roster change set already full")
        
        if any(True for change in self.roster_changes if change["player_out"] == player_out 
                or change["player_in"] == player_in):
            raise RosterException("Having same player in/out on multiple roster changes not supported")
           
        if isinstance(change_date, datetime.date):
            date_string = str(change_date)
        else:
            date_string = np.datetime_as_string(change_date, unit='D')
        equality_score = "O{}I{}D{}".format(player_out, player_in,
                                            date_string)
        self.roster_changes.append({"player_out": player_out, "player_in": player_in, "change_date": change_date, "equality_score":equality_score})
        self._compute_equality_score()
        self.score = None
            

    def replace(self, old_roster_change, new_roster_change):

        if new_roster_change is not None:
            # if we are removing same player in these 2 changes, this will be valid
            try:
                if old_roster_change is not None and new_roster_change['player_out'] == old_roster_change['player_out']:
                    pass
                elif new_roster_change['player_out'] in [rc['player_out'] for rc in self.roster_changes]:
                    raise RosterException("Having same player out on multiple roster changes not supported")
            except TypeError as e:
                self.log.exception(e)
            if (old_roster_change is not None and new_roster_change['player_in'] != old_roster_change[
                'player_in']) and (
                    new_roster_change['player_in'] in [rc['player_in'] for rc in self.roster_changes]):
                raise RosterException("Having same player in on multiple roster changes not supported")
        if old_roster_change is not None:
            self.roster_changes = [rc for rc in self.roster_changes if rc['player_out'] != old_roster_change['player_out']]
            self.score = None
        if new_roster_change is not None:
            self.add(new_roster_change['player_out'], new_roster_change['player_in'], new_roster_change['change_date'])
            self.score = None

    def get(self, date):
        return [change for change in self.roster_changes if change['change_date'] == date]

    def get_changes(self):
        return self.roster_changes

from json import JSONEncoder

class RosterChangeSetEncoder(JSONEncoder):
        def default(self, o):
            return o.__dict__



class RosterException(Exception):
    def __init__(self, *args):
        if args:
            self.message = args[0]
        else:
            self.message = None

    def __str__(self):
        if self.message:
            return 'MyCustomError, {0} '.format(self.message)
        else:
            return 'MyCustomError has been raised'
