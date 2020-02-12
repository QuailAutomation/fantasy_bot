#!/bin/python

import timeit
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
generations = 100
ELITE_NUM = int(5)


def profile(fnc):
    """A decorator that uses cProfile to profile a function"""

    def inner(*args, **kwargs):
        pr = cProfile.Profile()
        pr.enable()
        retval = fnc(*args, **kwargs)
        pr.disable()
        s = io.StringIO()
        sortby = 'cumulative'
        ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
        ps.print_stats()


def optimize_with_genetic_algorithm(score_comparer, roster_bldr,
                                    avail_plyrs, locked_plyrs):
    """
    Loader for the GeneticAlgorithm class

    See GeneticAlgorithm.__init__ for parameter type descriptions.
    """
    algo = GeneticAlgorithm(score_comparer, roster_bldr, avail_plyrs,
                            locked_plyrs)
    return algo.run(generations)


class GeneticAlgorithm:
    """
    Optimize the lineup using a genetic algorithm

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
    :param roster_bldr: Object that is used to construct a roster given the
    constraints of the league
    :type roster_bldr: roster.Builder
    :param avail_plyrs: Pool of available players that can be included in
    a lineup
    :type avail_plyrs: DataFrame
    :param locked_plyrs: Players that must exist in the optimized lineup
    :type locked_plyrs: list
    :return: If a better lineup was found, this will return it.  If no better
    lineup was found this returns None
    :rtype: list or None
    """

    def __init__(self, score_comparer, roster_bldr, avail_plyrs,
                 locked_plyrs):
        # self.cfg = cfg
        self.logger = logging.getLogger()
        self.score_comparer = score_comparer
        self.roster_bldr = roster_bldr
        self.ppool = avail_plyrs
        self.population = []
        self.locked_ids = [e["player_id"] for e in locked_plyrs]
        self.oppenents_estimates = score_comparer.opp_sum
        self.league = score_comparer.league
        # TODO this should be loaded from league
        self.player_stats = ["G", "A", "+/-", "PIM", "SOG", "FW", "HIT"]
        start_date, end_date = self.league.week_date_range(score_comparer.week)
        self.date_range = pd.date_range(start_date, end_date)
        # need what dates we can still do things when running during the week
        first_change_date = self.league.edit_date()
        if self.date_range[0] > first_change_date:
            first_change_date = self.date_range[0]
        self.my_team: Team = self.league.to_team(self.league.team_key())
        self.date_range_for_changes = pd.date_range(first_change_date, self.date_range[-1])
        self.waivers = self.league.waivers()
        self.droppable_players = self._generate_droppable_players()
        self.team_full_roster = self.league.to_team(self.league.team_key()).roster()

        self.my_scorer: BestRankedPlayerScorer = BestRankedPlayerScorer(self.league, self.my_team,
                                                                        self.ppool, self.date_range)
        self.roster_changes_allowed = 4 - self._get_num_roster_changes_made()

    def run(self, generations):
        """
        Optimize a lineup by running the genetic algorithm

        :param generations: The number of generations to run the algorithm for
        :type generations: int
        :return: The best lineup we generated.  Or None if no lineup was
        generated
        :rtype: list or None
        """

        self._init_progress_bar(generations)
        self._init_population()
        self.population = sorted(self.population, key=lambda e: e.score, reverse=True)
        if len(self.population) == 0:
            return None
        for generation in range(generations):
            if generation % 2 == 0:
                best = self.population[0]
                print("Best as of: {}, pop len: {}".format(generation, len(self.population)))
                print('player_out, player_in, change_date')
                self._print_roster_change_set(best)
                print(self.my_scorer.score(best).sum().to_dict())
                print("Summary:\n{}".format(best.scoring_summary.head(20)))
            self._update_progress(generation)
            self._mate()
            self._mutate()
            unscored = [rc for rc in self.population if rc.score is None]
            self._set_scores(unscored)

            self.population = sorted(self.population, key=lambda e: e.score, reverse=True)

        self.logger.info(
            "Ended with population size of {}".format(len(self.population)))
        return self.population[0]

    def _print_roster_change_set(self, roster_changes):
        print("Suggestions for roster changes")
        print("Score: {}".format(roster_changes.score))
        for _, row in roster_changes.roster_changes.iterrows():
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
                print(e)
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
        Shows progress of the lineup selection

        :param generation: Current generation number
        :param generations: Max number of generations
        """
        self.pbar.update(generation + 1)

    def _get_num_roster_changes_made(self):
        # if the game week is in the future then we couldn't have already made changes
        if datetime.date.today() < self.date_range[0]:
            return 0

        def retrieve_attribute_from_team_info(team_info, attribute):
            for attr in team_info:
                if attribute in attr:
                    return attr[attribute]

        raw_matchups = self.league.matchups()
        team_id = self.my_team.team_key.split('.')[-1]
        num_matchups = raw_matchups['fantasy_content']['league'][1]['scoreboard']['0']['matchups']['count']
        for matchup_index in range(0, num_matchups):
            matchup = raw_matchups['fantasy_content']['league'][1]['scoreboard']['0']['matchups'][str(matchup_index)]
            for i in range(0, 2):
                try:
                    if retrieve_attribute_from_team_info(matchup['matchup']['0']['teams'][str(i)]['team'][0],
                                                         'team_id') == team_id:
                        return int(
                            retrieve_attribute_from_team_info(matchup['matchup']['0']['teams'][str(i)]['team'][0],
                                                              'roster_adds')['value'])
                except TypeError as e:
                    pass
        assert False, 'Did not find roster changes for team'

    def _init_population(self):
        self.population = []
        self.last_mutated_roster_change = None
        selector = self._gen_player_selector(gen_type='pct_own')
        self._generate_roster_change_sets(selector, max_lineups)

        selector = self._gen_player_selector(gen_type='random')
        for _ in range(max_lineups * 2):
            if len(self.population) >= max_lineups:
                break
            self._generate_roster_change_sets(selector, max_lineups)

    def _generate_seed_lineup(self, locked_plyrs):
        """

        Generate an initial lineup of all of the locked players

        :return: Initial seed lineup
        :rtype: list
        """
        lineup = []
        for plyr in locked_plyrs:
            try:
                lineup = self.roster_bldr.fit_if_space(lineup, plyr)
            except LookupError:
                assert (False), \
                    "Initial set of locked players cannot fit into a single " \
                    "lineup.  Lineup has {} players already.  Trying to fit " \
                    "{} players.".format(len(lineup), len(locked_plyrs))
        return lineup

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
        else:
            assert (gen_type == 'random')
            selector.shuffle()
        return selector

    def _add_completed_lineup(self, lineup):
        assert (len(lineup) == self.roster_bldr.max_players())
        sids = self._to_sids(lineup)
        if self._is_dup_sids(sids):
            return
        score = self.score_comparer.compute_score(lineup),
        self.population.append({'players': lineup,
                                'score': score,
                                'id': self._gen_lineup_id(),
                                'sids': sids})

    def _fit_plyr_to_change_set(self, plyer, change_set):
        fit = True
        for change in change_set:
            if change.player_in == plyer:
                fit = False
                break
        return fit

    def _generate_roster_change_sets(self, selector, max_roster_change_sets):
        # how many roster changes have been made so far
        # when is next date we can make roster changes for ?
        # adjust date range so doesn't try for roster changes earlier in week
        assert (len(self.population) < max_roster_change_sets)
        team_roster = pd.DataFrame(self.team_full_roster)
        roster_change_sets = self.population
        last_roster_change_set: RosterChangeSet = RosterChangeSet(max_allowed=self.roster_changes_allowed)
        for plyr in selector.select():
            fit = False
            if len(self.population) == max_roster_change_sets:
                break

            if plyr['player_id'] in team_roster.player_id.values or plyr['position_type'] == 'G':
                continue

            drop_date = random.choice(self.date_range_for_changes).date()

            if last_roster_change_set.is_full():
                if last_roster_change_set not in self.population:
                    roster_change_sets.append(last_roster_change_set)
                last_roster_change_set = RosterChangeSet(max_allowed=self.roster_changes_allowed)

            while not last_roster_change_set.is_full():
                # let's pick someone to remove
                while True:
                    player_to_remove = random.choice(self.droppable_players)
                    valid_positions = self.ppool.at[player_to_remove, 'position_type']
                    if valid_positions is not None and 'G' not in valid_positions:
                        break
                if last_roster_change_set.can_drop_player(player_to_remove):
                    # create a roster change
                    try:
                        last_roster_change_set.add(player_to_remove, plyr['player_id'], drop_date)
                    except Exception as e:
                        print(e)
                break

        # start_week, end_week = self.league.week_date_range(self.league.current_week())

        # score each of the change sets
        for index, change_set in enumerate(roster_change_sets):
            if change_set.score is None:
                self._set_scores([change_set])
                if index % 19 == 0:
                    print("scored: {}, ({})".format(index, change_set.score))
            pass
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
        for lineup in self.population[1:]:
            assert (lineup.score is not None)
            if lineup.score > best_lineup.score:
                best_lineup = lineup
        return best_lineup

    def _mate(self):
        """
        Merge two lineups to produce children that character genes from both

        The selection process regarding who to mate is determined using the
        selectionStyle config parameter.
        """
        new_pop = []
        for elite in self.population[:ELITE_NUM + 1]:
            new_pop.append(elite)

        attempt = 0
        while len(new_pop) < len(self.population) and attempt < len(self.population) * 2:
            attempt += 1
            mates = self._pick_lineups()
            if mates:
                if mates[0] == mates[1]:
                    pass
                # self._remove_from_pop(mates[0])
                # self._remove_from_pop(mates[1])
                offspring = self._produce_offspring(mates)
                # for i, lineup in enumerate(offspring):
                #     self._log_lineup("Offspring " + str(i), lineup)
                for off in offspring:
                    # if off not in new_pop:
                    new_pop.append(off)
            # self.population = self.population + offspring
        self.population = new_pop

    def _pick_lineups(self):
        """
        Pick two lineups at random

        This uses the tournament selection process where random set of lineups
        are selected, then go through a tournament to pick the top number.

        :return: List of lineups.  Return None if not enough lineups exists.
        """
        k = int(4)
        if k > len(self.population):
            pw = math.floor(math.log(len(self.population), 2))
            k = 2 ** pw
        assert (math.log(k, 2).is_integer()), "Must be a power of 2"
        participants = random.sample(self.population, k=k)
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
            self.logger.warning("_pick_lineups is returning the same participants")
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
        # let's remove second 1/2 of roster changes in first parent.  will add those to other parent.
        num_roster_changes_to_remove = int(len(mates[0]) / 2)

        changes_to_remove = mates[0][-num_roster_changes_to_remove:]
        # del(mates[0][-num_roster_changes_to_remove:])
        # lets remove second 1/2 of roster changes in second, add those to 1st parent
        num_roster_changes_to_remove_2 = int(len(mates[1]) / 2)
        changes_to_remove_2 = mates[1][-num_roster_changes_to_remove_2:]
        # del (mates[1][-num_roster_changes_to_remove:])

        offspring = []
        offspring1 = RosterChangeSet(
            max_allowed=len(mates[0]) - num_roster_changes_to_remove + num_roster_changes_to_remove_2)
        try:
            for change in mates[0].get_changes().iloc[len(mates[0]) - num_roster_changes_to_remove:, :].itertuples():
                offspring1.add(change.player_out, change.player_in, change.change_date)
            if num_roster_changes_to_remove_2 > 0:
                for change in changes_to_remove_2.itertuples():
                    offspring1.add(change.player_out, change.player_in, change.change_date)
            offspring.append(offspring1)
        except:
            # print("Offspring rejected, player already going in/out")
            offspring.append(mates[0])

        offspring2 = RosterChangeSet(
            max_allowed=len(mates[1]) - num_roster_changes_to_remove_2 + num_roster_changes_to_remove)
        try:
            for change in mates[1].get_changes().iloc[0:-num_roster_changes_to_remove_2:, :].itertuples():
                offspring2.add(change.player_out, change.player_in, change.change_date)
            if num_roster_changes_to_remove > 0:
                for change in changes_to_remove.itertuples():
                    offspring2.add(change.player_out, change.player_in, change.change_date)
            offspring.append(offspring2)
        except:
            # print('Offspring rejected, player in or out exists')
            offspring.append(mates[1])
        # print("Offspring rejected, player already going in/out")

        # offspring = [offspring1, offspring2]
        # self._set_scores(offspring)

        # offspring = sorted(offspring, key=lambda e: e.score, reverse=True)
        # Remove any identical offspring.  If two offspring are identical they
        # will be adjacent to each other because they have the same score.
        # for i in range(len(offspring) - 1, 0, -1):
        #     if offspring[i] == offspring[i - 1]:
        #         del (offspring[i])
        # if len(offspring) < 2:
        #     pass
        # Check for duplicate lineups in the general population
        # while self._is_dup_sids(offspring[0]['sids']):

        # if len(offspring) > 0:
        #     if offspring[0] in self.population:
        #         del(offspring[0])
        #     if offspring[-1] in self.population:
        #         del (offspring[-1])
        return offspring[0:2]

    def _set_scores(self, roster_change_sets):
        # my_scorer: BestRankedPlayerScorer = BestRankedPlayerScorer(self.team_full_roster,
        #                                                            self.ppool, self.date_range)
        # score each of the change sets
        for change_set in roster_change_sets:
            the_score = self.my_scorer.score(change_set)
            change_set.scoring_summary = the_score
            change_set.score = self.score_comparer.compute_score(the_score.loc[:, self.player_stats].sum())

    def _mutate_roster_change(self, lineup, selector, team_roster):
        try:
            roster_change_to_mutate_index = random.randint(1, len(lineup)) - 1

            roster_change_to_mutate = lineup[roster_change_to_mutate_index]
            # lets mutate this change set
            random_number = random.randint(1, 100)
            if len(self.date_range_for_changes) > 1 and random_number < 30:
                # lets mutate date
                while True:
                    drop_date = random.choice(self.date_range_for_changes).date()


                    if drop_date != roster_change_to_mutate.change_date:
                        mutated_roster_change = [roster_change_to_mutate.player_out,
                                                 roster_change_to_mutate.player_in,
                                                 drop_date]
                        lineup.replace(roster_change_to_mutate, mutated_roster_change)
                        # print('mutated date')
                        break

                pass

            elif random_number < 40:
                # lets mutate player out
                for _ in range(50):
                    player_to_remove = random.choice(self.droppable_players)
                    proposed_player_exists = any(rc.player_out == player_to_remove for rc in lineup)
                    if not proposed_player_exists:
                        mutated_roster_change = [player_to_remove, roster_change_to_mutate.player_in,
                                                 roster_change_to_mutate.change_date]

                        # move lineup, add this mutated
                        # del (lineup[roster_change_to_mutate_index])
                        # lineup.add(mutated_roster_change)
                        lineup.replace(roster_change_to_mutate, mutated_roster_change)
                        # print("Mutated player out")

                        break
            elif random_number < 80:
                # lets mutate player in
                for plyr in selector.select():
                    if plyr['player_id'] in team_roster.player_id.values or plyr['position_type'] == 'G':
                        continue
                    if not any(rc.player_in == plyr['player_id'] for rc in lineup):
                        # print("Have player to add")
                        mutated_roster_change = [roster_change_to_mutate.player_out, plyr['player_id'],
                                                 roster_change_to_mutate.change_date]
                        lineup.replace(roster_change_to_mutate, mutated_roster_change)
                        break
            elif 80 < random_number < 85:
                # remove a roster change - don't have to worry about zero roster changes, eliminated 0 ones already
                del (lineup[roster_change_to_mutate_index])
            else:
                # add a new roster change
                # print("Implement adding new roster change to set: {}, index: {}".format(random_number, index) )
                pass
            self._set_scores([lineup])
        except ValueError as e:
            print(e)
            pass

    def _mutate(self):
        """
        Go through all of the players and mutate a certain percent.
        Mutation simply means swapping out the player with a random player.
        """

        mutate_pct = 2
        add_lineups = []
        rem_lineups = []
        selector = self._gen_player_selector(gen_type='random')
        team_roster = pd.DataFrame(self.team_full_roster)

        to_mutate = random.sample(self.population[ELITE_NUM:], int((len(self.population) - ELITE_NUM) * 2/100))
        for rc in to_mutate:
            self._mutate_roster_change(rc, selector, team_roster)
            if rc.score is None:
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

    def __init__(self, changes=None, max_allowed=None):
        self.number_roster_changes = random.randint(0,max_allowed) if max_allowed is None else max_allowed

        # date, list changes
        self.roster_changes = pd.DataFrame(columns=['change_date', 'player_out', 'player_in', 'equality_score'])
        self.equality_value = None
        self.score = None
        if changes is not None:
            for change in changes.itertuples():
                self.add(change.player_out, change.player_in, change.change_date)
        super().__init__()


    def __deepcopy__(self, memodict={}):
        cloned_roster_changes = self.roster_changes.copy()

        return RosterChangeSet(cloned_roster_changes)
        # new_rc_set = RosterChangeSet()


    def __getitem__(self, i):
        try:
            return self.roster_changes.iloc[i]
        except TypeError:
            pass


    def __len__(self):
        return len(self.roster_changes)


    def _compute_equality_score(self):
        self.equality_value = "RC" + self.roster_changes.loc[:, 'equality_score'].str.cat()


    def __eq__(self, other):
        if self.equality_value is None:
            self.equality_value = self._compute_equality_score()
        if isinstance(other,RosterChangeSet):
            return self.equality_value == other.equality_value
        else:
            return False


    def __delitem__(self, key):
        self.roster_changes.drop(self.roster_changes.index[key], inplace=True)
        self._compute_equality_score()


    def can_drop_player(self, drop_player):
        return len(self.roster_changes) < self.number_roster_changes and drop_player not in self.roster_changes.loc[:,
                                                                                            'player_out'].values


    def add(self, player_out, player_in, change_date):
        if len(self.roster_changes.index) < self.number_roster_changes:
            if player_out in self.roster_changes.loc[:, 'player_out'].values or player_in in self.roster_changes.loc[:,
                                                                                      'player_in'].values:
                raise Exception("Having same player in/out on multiple roster changes not supported")
            if isinstance(change_date, datetime.date):
                date_string = str(change_date)
            else:
                date_string = np.datetime_as_string(change_date, unit='D')
            equality_score = "O{}I{}D{}".format(player_out, player_in,
                                                date_string)
            self.roster_changes.loc[len(self.roster_changes)] = [change_date, player_out, player_in, equality_score]
            self._compute_equality_score()
        else:
            raise Exception("Roster change set already full")


    def replace(self, old_roster_change, new_roster_change):
        self.roster_changes.drop(
            self.roster_changes[self.roster_changes.player_out == old_roster_change['player_out']].index, inplace=True)
        self.add(*new_roster_change)


    def is_full(self):
        return len(self.roster_changes) == self.number_roster_changes


    def get(self, date):
        return self.roster_changes[self.roster_changes['change_date'] == date]


    def get_changes(self):
        return self.roster_changes
