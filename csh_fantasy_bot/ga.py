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

    def __init__(self, all_players, valid_dates, num_moves, add_selector, drop_selector):
        self.all_players = all_players
        self.max_n_moves = num_moves
        self.valid_dates = valid_dates
        self.add_selector = add_selector
        self.drop_selector = drop_selector
        self.log = logging.getLogger(__name__)
        self.added_no_changes = False
    
    def createChromosome(self):
        """Create a roster change set."""
        rcs = RosterChangeSet()
        if self.added_no_changes:
            roster_changes = random.randint(1, self.max_n_moves)
            while len(rcs) < roster_changes:
                drop_date = random.choice(self.valid_dates).date()
                player_to_add = self.add_selector.select()
                player_to_drop = self.drop_selector.select()
                with suppress(RosterException):
                    rcs.add(RosterChange(player_to_drop.index.values[0], player_to_add.index.values[0], drop_date, player_to_add))
        else:
            # let's always start with no changes at all
            self.added_no_changes = True
        return rcs

    def pretty_print_rcs(self, rcs):
        for rc in rcs.roster_changes:
            print('in loop')
            print(f"Out id: {rc.out_player_id}-{self.drop_selector.df.loc[rc.out_player_id, 'name']}-({round(self.drop_selector.df.loc[rc.out_player_id, 'fpts'],3)}) "
                 + f"in: {rc.in_player_id}-{self.add_selector.df.loc[rc.in_player_id, 'name']}-({round(self.add_selector.df.loc[rc.in_player_id, 'fpts'],3)}) "
                 + f"change date: {rc.change_date}")

class RandomWeightedSelector:
    """Random sampling of rows based on column in dataframe."""

    def __init__(self, df, column, inverse=False):
        self.df = df.copy()
        self.column = column
        self.normalized_column_name = f'{self.column}_normalized'
        self._normalize(self.df, column, inverse)
        
    def select(self):
        """Select random weighted row."""
        return self.df.sample(1,weights=self.df[self.normalized_column_name])

    def _normalize(self, df, column, inverse=False):
        # add support for -ve numbers too.  find min and add that to value to get to 0
        minimum_value = df[column].min() - .2
        #  if we have negatives, we must bump them up to eliminate them
        if minimum_value > .2:
            minimum_value = 0

        df[f'{column}_non_zero'] = 0
        # if we don't have projections, their std scores end up at zero, which is higher than some players
        # because it can be negative.  We are going to add the min std sum for each player, then normalize, 
        # then zero out the player for which we don't have projections
        df.loc[df.G.notnull(),f'{column}_non_zero'] = df[column] - minimum_value
        sum_total = df[f'{column}_non_zero'].sum()
        if inverse:
            df[f'{column}_normalized'] = (1/df['fpts_non_zero'])/(1/df['fpts_non_zero']).sum()
            # df[f'{column}_normalized'] = df[f'{column}_normalized']/df[f'{column}_normalized'].sum()  
        else:
            df[f'{column}_normalized'] = df[f'{column}_non_zero']/sum_total

        # TODO this will break for Goalies.  Should and with GAA or some other goalie stat i think     
        df.loc[df.G.isnull(),f'{column}_normalized'] =  0

from csh_fantasy_bot.tasks import score


def fitness(roster_change_sets, all_players, date_range, scoring_categories, score_comparer, team_key):
    """Score the roster change set."""
    # store the id so we can match back up after serialization
    team_id = int(team_key.split('.')[-1])
    for rcs in roster_change_sets:
        rcs._id = id(rcs) 
    log.debug("starting chunk scoring")
    unscored_change_sets = [rc for rc in roster_change_sets if rc.score is None]
    results = score_chunk(all_players[(all_players.fantasy_status == team_id)], date_range[0], date_range[-1], unscored_change_sets, scoring_categories, team_key=team_key)
    log.debug("Done chunk scoring")

    scores_dict = {_id:score for _id,score in results}
    log.debug("computing roster change scores")
    for change_set in unscored_change_sets:
        try:
            scoring_result = scores_dict[change_set._id]
            change_set.scoring_summary = scoring_result.reset_index()
            # change_set.score = score_comparer.compute_score(scoring_result)
            score = score_comparer.score(scoring_result).loc['score_opp'].sum()
            change_set.score = score
        except KeyError as e:
            log.exception(e)
        
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