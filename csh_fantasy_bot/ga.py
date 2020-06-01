"""Custom code for GA."""
import random
import logging 
from contextlib import suppress

from pygenetic import ChromosomeFactory, GAEngine

from csh_fantasy_bot.league import FantasyLeague
from csh_fantasy_bot.roster_change_optimizer import RosterChangeSet, RosterException, RosterChange
from csh_fantasy_bot.tasks import score_chunk

log = logging.getLogger(__name__)

class RosterChangeSetFactory(ChromosomeFactory.ChromosomeFactory):
    """Factory to create roster change sets."""

    def __init__(self, all_players, valid_dates, scoring_categories, team_id, num_moves):
        self.all_players = all_players
        self.team_id = team_id
        self.num_moves = num_moves
        self.valid_dates = valid_dates
        self.scoring_categories = scoring_categories
        fantasy_players = all_players[all_players.position_type == 'P']
        self.add_selector = RandomWeightedSelector(fantasy_players[fantasy_players.fantasy_status == 'FA'],'fpts')
        self.drop_selector = RandomWeightedSelector(all_players[(all_players.fantasy_status == team_id) & (all_players.percent_owned < 93)], 'fpts', inverse=True)
        self.log = logging.getLogger(__name__)
    
    def createChromosome(self):
        """Create a roster change set."""
        roster_changes = random.randint(0, self.num_moves)
        rcs = RosterChangeSet()
        while len(rcs) < roster_changes:
            try:
                drop_date = random.choice(self.valid_dates).date()
            except IndexError as e:
                self.log.exception(e)

            player_to_add = self.add_selector.select()
            player_to_drop = self.drop_selector.select()
            with suppress(RosterException):
                rcs.add(RosterChange(player_to_drop.index.values[0], player_to_add.index.values[0], drop_date, player_to_add[self.scoring_categories]))

        return rcs


class RandomWeightedSelector:
    """Random sampling of rows based on column in dataframe."""

    def __init__(self, df, column, inverse=True):
        self.df = df.copy()
        self.column = column
        self._normalize(self.df, column, inverse)
        self.normalized_column_name = f'{self.column}-normalized'
        
    def select(self):
        """Select random weighted row."""
        return self.df.sample(1,weights=self.normalized_column_name)

    def _normalize(self, df, column, inverse=False):
        if inverse:
            df[f'{column}-normalized'] = 1 - (df[column] / df[column].sum()) 
            df[f'{column}-normalized'] = df[f'{column}-normalized']/df[f'{column}-normalized'].sum()  
        else:
            df[f'{column}-normalized'] = df[column]/df[column].sum()

from csh_fantasy_bot.tasks import score


def fitness(roster_change_sets, all_players, date_range, scoring_categories, score_comparer, team_id):
    """Score the roster change set."""
    # store the id so we can match back up after serialization
    for rcs in roster_change_sets:
        rcs._id = id(rcs) 
    log.debug("starting chunk scoring")
    results = score_chunk(all_players[(all_players.fantasy_status == team_id)], date_range[0], date_range[-1], roster_change_sets, scoring_categories)
    log.debug("Done chunk scoring")
    scores_dict = {_id:score for _id,score in results}
    log.debug("computing roster change scores")
    for change_set in roster_change_sets:
        try:
            scoring_result = scores_dict[change_set._id]
        except KeyError as e:
            log.exception(e)
        change_set.scoring_summary = scoring_result.reset_index()
        change_set.score = score_comparer.compute_score(scoring_result)
    log.debug('Done computing roster scores')
    return [(change_set, change_set.score) for change_set in roster_change_sets]


class CeleryFitnessGAEngine(GAEngine.GAEngine):
    def generateFitnessMappings(self):
        """
        Generates a list of tuples (individual, fitness_score) and also stores the tuple
        containing fittest chromosome [best_fitness] depending on fitness_type(max/min/equal)

        """
        self.fitness_mappings = self.calculateFitness(self.population.members)
        if type(self.fitness_type) == str:
            if self.fitness_type == 'max':
                self.fitness_mappings.sort(key=lambda x:x[1],reverse=True)
                self.best_fitness = self.fitness_mappings[0]
                if self.hall_of_fame:
                    if self.best_fitness[1] > self.hall_of_fame[1]:
                        self.hall_of_fame = self.best_fitness
                else:
                    self.hall_of_fame = self.best_fitness

            elif self.fitness_type == 'min':
                self.fitness_mappings.sort(key=lambda x:x[1])
                self.best_fitness = self.fitness_mappings[0]
                if self.hall_of_fame:
                    if self.best_fitness[1] < self.hall_of_fame[1]:
                        self.hall_of_fame = self.best_fitness
                else:
                    self.hall_of_fame = self.best_fitness

        elif type(self.fitness_type) == tuple or type(self.fitness_type) == list:
            self.fitness_mappings.sort(key=lambda x:abs(x[1]-self.fitness_type[1]))
            self.best_fitness = self.fitness_mappings[0]
            if self.hall_of_fame:
                if abs(self.fitness_type[1] - self.best_fitness[1]) < abs(self.fitness_type[1] - self.hall_of_fame[1]):
                    self.hall_of_fame = self.best_fitness
            else:
                self.hall_of_fame = self.best_fitness