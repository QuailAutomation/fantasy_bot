"""Custom code for GA."""
import random
import logging 
from contextlib import suppress

from pygenetic import ChromosomeFactory, GAEngine

from csh_fantasy_bot.league import FantasyLeague
from csh_fantasy_bot.roster_change_optimizer import RosterChangeSet, RosterException
from csh_fantasy_bot.tasks import score_chunk

class RosterChangeSetFactory(ChromosomeFactory.ChromosomeFactory):
    """Factory to create roster change sets."""

    def __init__(self, all_players, team_id, valid_dates, num_moves):
        self.all_players = all_players
        self.team_id = team_id
        self.num_moves = num_moves
        self.valid_dates = valid_dates
        fantasy_players = all_players[all_players.position_type == 'P']
        self.add_selector = RandomWeightedSelector(fantasy_players[fantasy_players.fantasy_status == 'FA'],'fpts')
        self.drop_selector = RandomWeightedSelector(all_players[(all_players.fantasy_status == team_id) & (all_players.percent_owned < 93)], 'fpts', inverse=True)
        self.log = logging.getLogger(__name__)
    
    def createChromosome(self):
        """Create a roster change set."""
        roster_changes = random.randint(0, self.num_moves)
        rcs = RosterChangeSet(self.valid_dates)
        while len(rcs) < roster_changes:
            try:
                drop_date = random.choice(self.valid_dates).date()
            except IndexError as e:
                self.log.exception(e)

            player_to_add = self.add_selector.select()
            player_to_drop = self.drop_selector.select()
            with suppress(RosterException):
                rcs.add(player_to_drop.index.values[0], player_to_add.index.values[0], drop_date)

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

def fitness(roster_change_sets, date_range, team_key, opponent_id):
    """Score the roster change set."""
    # store the id so we can match back up after serialization
    for rcs in roster_change_sets:
        rcs._id = id(rcs) 

    results = score_chunk(team_key, date_range[0], date_range[-1], roster_change_sets, opponent_id)
    # don't use parallel
    # score = league.score(date_range,team_key, opponent_id,[chromosome])
    # assert(len(results) == 1)
    # we do some serializing of the chromosome, so remap score back to orig using equality value
    scores_dict = {rcs._id:rcs.score for rcs in results}
    return [(change_set, scores_dict[change_set._id]) for change_set in roster_change_sets]
    # chromosome.score = results[0].score
    # chromosome.scoring_summary = results[0].scoring_summary
    # return results[0].score


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