#!/usr/bin/python
import copy
import logging
import numpy as np
from collections import namedtuple, defaultdict
from functools import partial

class Container:
    """Class that holds a roster of players

    :param lg: Yahoo! league
    :type lg: yahoo_fantasy_api.league.League
    :param team: Yahoo! Team to do the predictions for
    :type team: yahoo_fantasy_api.team.Team
    """
    def __init__(self, lg, team):
        if lg is not None:
            self.week = lg.current_week() + 1
            if self.week > lg.end_week():
                raise RuntimeError("Season over no more weeks to predict")
            full_roster = team.roster(self.week)
            self.roster = [e for e in full_roster
                           if e["selected_position"] not in ["IR"] and e['position_type'] != 'G']
        else:
            self.roster = []

    def get_roster(self):
        return self.roster

    def del_player(self, player_name):
        """Removes the given player from your roster

        :param player_name: Full name of the player to delete.  The player name
               must this exactly; with the exception of accents, which are
               normalized out
        :type player_name: str
        """
        for plyr in self.roster:
            if utils.normalized(player_name) == utils.normalized(plyr['name']):
                self.roster.remove(plyr)

    def player_exists(self, player_name):
        """Check if the given player is on your roster

        :param player_name: The player name to check
        :type player_name: string
        :return: True if the player, False otherwise
        :rtype: boolean
        """
        for plyr in self.roster:
            if player_name == utils.normalized(plyr['name']):
                return True
        return False

    def get_position_type(self, pos):
        if pos in ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "Util"]:
            return 'B'
        elif pos in ["SP", "RP"]:
            return 'P'
        else:
            raise ValueError("{} is not a valid position".format(pos))

    def add_player(self, player_name, pos):
        """Adds a player to the roster

        This will raise an error if the player already exists on the roster.

        :param player_name: Full name of the player to add.
        :type player_name: str
        :param pos: The short version of the selected position.
        :type pos: str
        """
        if self.player_exists(player_name):
            raise ValueError("Player is already on the roster")

        self.roster.append({'position_type': self.get_position_type(pos),
                            'selected_position': pos,
                            'name': player_name,
                            'player_id': -1})

    def add_players(self, players):
        """Adds multiple players in bulk.

        :param players: List of players to add to the container
        :type players: List(dict)
        """
        self.roster = self.roster + players

    def change_position(self, player_name, pos):
        """Change the position of a player

        The player must be on your roster.

        :param player_name: Full name of the player who's position is changing
        :type player_name: str
        :param pos: The short version of the position.
        :type pos: str
        """
        for plyr in self.roster:
            if utils.normalized(player_name) == utils.normalized(plyr['name']):
                plyr['selected_position'] = pos
                return
        raise ValueError("Player not found on roster")


class Builder:
    """Class that generates roster permuations suitable for evaluation"""
    def __init__(self, positions):
        self.logger = logging.getLogger()
        self.positions = positions
        self.pos_count = {}
        for p in positions:
            if p in self.pos_count:
                self.pos_count[p] += 1
            else:
                self.pos_count[p] = 1

    def fit_if_space(self, roster, player):
        """Fit a player onto a roster if there is space.

        The input roster must have the following columns:
            - eligible_positions: array of positions that the player can play
            - selected_position: the selected position we chose for the roster

        If successful, the result will be a roster with the new player added to
        it with a selected_position set to something non-NaN.

        :param roster: Roster to fit the player on.
        :type roster: list
        :param player: Player to try and find a roster spot for.
        :type player: pandas.Series
        :return: The new roster with the player in it.  If an open spot is not
        available for the player then an LookupError assertion is returned.
        :rtype: list
        """
        rpos = {}
        for p in roster:
            if p['selected_position'] in rpos:
                rpos[p['selected_position']] += 1
            else:
                rpos[p['selected_position']] = 1
        self.logger.debug("Roster positions: {}".format(rpos))
        self.logger.debug("Fit {}: positions={}".format(
            player['name'], player['eligible_positions']))
        # Search if any of the players eligible_positions are open.  Then it is
        # an easy fit.
        for pos in player.eligible_positions:
            if self._has_empty_position_slot(roster, pos):
                self.logger.debug("Fit at empty position: {}".format(pos))
                player.selected_position = pos
                roster.append(player)
                return roster

        # List to keep track of the players swapped in a given fit.  This
        # ensures the same player isn't moved more than once in a given
        # sequence of swaps.
        swapped_plyrs = []

        # Look through the other players already starting at the new players
        # positions.  If any of them can move to empty spot then we can fit.
        for pos in player.eligible_positions:
            for occurance in range(self.pos_count[pos]):
                self.logger.debug("Attempt swap at position: {}".format(pos))
                plyr_at_pos = self._get_player_by_pos(roster, pos, occurance)
                self.logger.debug("Swap out {}: {}".format(
                    plyr_at_pos['name_x'], pos))
                if self._swap_eligible_pos_recurse(roster, plyr_at_pos,
                                                   swapped_plyrs):
                    assert(self._has_empty_position_slot(roster, pos))
                    self.logger.debug('{}: {} -> {}'.format(
                        player['name_x'], player['selected_position'], pos))
                    player.selected_position = pos
                    roster.append(player)
                    return roster

        raise LookupError("No space for player on roster")

    def enumerate_fit(self, roster, player):
        """Generate possible enumerations by fitting the player on the roster

        This function will actively remove players in order to get the player
        to fit.

        :param roster: Base roster to try and add the player too
        :type roster: list
        :param player: Player to try and fit into the roster
        :type player: pandas.Series
        :return: An iterable that will enumerate all possible roster
        combinations to get the player to fit.
        :rtype: iterable
        """
        for pos in self.pos_count.keys():
            for occurance in range(self.pos_count[pos]):
                orig_roster = copy.deepcopy(roster)
                pos_player = self._get_player_by_pos(roster, pos, occurance)
                if pos_player is None:
                    continue
                pos_player.selected_position = np.nan
                try:
                    new_roster = self.fit_if_space(roster, player)

                    # Remove anyone from the roster that doesn't have a
                    # selected position
                    pruned_roster = []
                    for plyr in new_roster:
                        if type(plyr['selected_position']) == str:
                            pruned_roster.append(plyr)

                    yield pruned_roster
                except LookupError:
                    pass
                finally:
                    roster = orig_roster
                    player.selected_position = np.nan

    def max_players(self):
        return len(self.positions)

    def _get_player_by_pos(self, roster, pos, occurance):
        cum_occurance = 0
        for plyr in roster:
            if plyr.selected_position == pos:
                if cum_occurance == occurance:
                    return plyr
                cum_occurance += 1
        return None

    def _get_num_players_at_pos(self, roster, pos):
        """Return the number of players the roster has at the given position"""
        cum_occurance = 0
        for plyr in roster:
            if plyr.selected_position == pos:
                cum_occurance += 1
        return cum_occurance

    def _has_empty_position_slot(self, roster, pos):
        # Not all positions may be tracked.  Player injury could be eligible to
        # go to the IR slot.
        if pos in self.pos_count:
            num = self._get_num_players_at_pos(roster, pos)
            return num < self.pos_count[pos]
        else:
            return False

    def _swap_eligible_pos_recurse(self, roster, player, swapped_plyrs):
        """Recursively swap positions with players until all positions are used.

        :param roster: The roster to work with
        :type roster: pandas.DataFrame
        :param player: The player to try and swap around.
        :type player: pandas.Series
        :param swapped_plyrs: A list of players already swapped in this
        sequence of trying to fit the player.
        :type swapped: list
        :return: True if we were able to swap to an empty position
        :rtype: Boolean
        """
        assert(player.selected_position is not None)

        if player['player_id'] in swapped_plyrs:
            return False
        swapped_plyrs.append(player['player_id'])

        # Check if player can change their position to an empty spot
        for pos in player.eligible_positions:
            if pos != player.selected_position:
                if self._has_empty_position_slot(roster, pos):
                    self.logger.debug('{}: {} -> {}'.format(
                        player['name'], player['selected_position'], pos))
                    player.selected_position = pos
                    return True

        # Recursively check each of the positions that the player plays to
        # see if they can switch out to an empty spot.
        for pos in player.eligible_positions:
            if pos != player.selected_position:
                for occurance in range(self.pos_count[pos]):
                    other_plyr = self._get_player_by_pos(roster, pos,
                                                         occurance)
                    assert(other_plyr is not None), "Nobody for " + pos
                    if self._swap_eligible_pos_recurse(roster, other_plyr,
                                                       swapped_plyrs):
                        assert(self._has_empty_position_slot(roster, pos))
                        self.logger.debug('{}: {} -> {}'.format(
                            player['name'], player['selected_position'], pos))
                        player.selected_position = pos
                        return True

        swapped_plyrs.pop()
        return False


class PlayerSelector:
    """Class that will select players from a container to include on a roster.

    The roster container it is given should be a pool of all available players
    that can make up a roster.  The players select are players that are tops
    in the stats categories.

    :param player_pool: Pool of players that we will pick from
    :type player_pool: Container
    """
    def __init__(self, player_pool):
        self.ppool = player_pool
        self.rank_stats_descending = ["ERA", "WHIP", "percent_owned"]

    def rank(self, stat_categories):
        """Rank players in the player pool according to the stat categories

        :param stat_categories: List of the stat categories that the fantasy
               league uses.
        :type stat_categories: list(str)
        """
        self.ppool['rank'] = 0
        for stat in stat_categories:
            self.ppool['rank'] += self.ppool[stat].rank(
                    ascending=self._is_stat_ascending(stat))
        self.ppool.sort_values(by=['rank'], ascending=False,inplace=True)
        pass

    def shuffle(self):
        """
        Shuffle the player pool in order to produce a random roster.
        """
        self.ppool = self.ppool.sample(frac=1).reset_index(drop=True)

    def select(self):
        """Iterate over players in the pool according to the rank.
        This is to be called after rank().  It will return the players starting
        with the top ranked player.
        """

        for plyr_tuple in self.ppool.iterrows():
            yield plyr_tuple[1]

    def _is_stat_ascending(self, stat):
        if stat in self.rank_stats_descending:
            return False
        else:
            return True

    def set_descending_categories(self, cats):
        self.rank_stats_descending = cats

import pandas as pd
import numpy as np
from itertools import combinations


class RecursiveRosterBuilder:
    """Builds bost roster of players using predicted stats and a weighting."""
    
    def __init__(self, roster_makeup=pd.Index("C,C,LW,LW,RW,RW,D,D,D,D".split(",")), stats_weights=None):
        """Initialize."""
        self.roster_makeup = roster_makeup
        
        # weight importance of the player stats
        if stats_weights is not None:
            self.player_stats = list(stats_weights.index.values)
            self.weights_series = stats_weights 
        else:
            self.player_stats = ["G", "A", "+/-", "PIM", "SOG", "FW", "HIT"]
            self.weights_series = pd.Series([1, .75, .5, .5, 1, .1, 1], index=self.player_stats)
            
        self.roster_position_counts = roster_makeup.value_counts()



    def _place_player(self, roster, player):
        for position in player.eligible_positions:
            if position not in self.full_positions:
                players_in_position = roster[position]
                if len(players_in_position) < self.roster_position_counts[position]:
                    roster[position].append(player)
                    return
                else:
                    # position is full, should see if earlier placed player can move
                    did_make_room = self._make_room(position, roster)
                    if did_make_room:
                        roster[position].append(player)
                        return
                    else:
                        self.full_positions.add(position)
                        # print('Position full: {}'.format(position))
                        pass


    def _make_room(self, position, roster, full_positions=None):
        for position_to_look_for_room in self.roster_makeup.unique():
            # is there a player in this position that can move
            for players in roster[position_to_look_for_room]:
                for other_possible_positions in players.eligible_positions:
                    if not 'IR' == other_possible_positions and (len(roster[other_possible_positions]) < \
                                    self.roster_position_counts[other_possible_positions] and \
                                    other_possible_positions != position_to_look_for_room):
                        roster[other_possible_positions].append(players)
                        roster[position_to_look_for_room].remove(players)
                        return True

    def find_best(self, sorted_players: pd.DataFrame, weights_series=None):
        """Determine roster with highest projected output using weights."""
        roster = defaultdict(list)
        for player in sorted_players.itertuples():
            self._place_player(roster, player)
        
        return pd.Series({".".join([k ,str(k2)]) :v2.Index \
                        for k,v in roster.items() \
                        for k2,v2 in zip(range(1, max(self.roster_position_counts)+1), v)})

    def find_best1(self, sorted_players, weights_series=None):
        """Determine roster with highest projected output using weights."""
        full_positions = set()
        daily_roster = defaultdict(list)
        for p in sorted_players:
            for position in p.eligible_positions:
                if position != 'IR' and position not in full_positions:
                    players_in_position = daily_roster[position]
                    if len(players_in_position) < self.roster_position_counts[position]:
                        daily_roster[position].append(p)
                        break
                    else:
                        # position is full, should see if earlier placed player can move
                        did_make_room = self._make_room(position, daily_roster)
                        if did_make_room:
                            daily_roster[position].append(p)
                            break
                        else:
                            full_positions.add(position)
                            # print('Position full: {}'.format(position))
                            pass
            
        return (RosteredPlayer(position=k, ordinal=k2, player_id=v2.Index) \
                        for k,v in daily_roster.items() \
                        for k2,v2 in zip(range(1, 10), v))


RosteredPlayer = namedtuple('RosteredPlayer', 'position ordinal player_id')

RosterPlayer = namedtuple('RosterPlayer', [
    'id',
    'eligible_positions',
    'fpts',
    ])

def combination_roster_optimization(team, roster_makeup, stats_weights):
    """Determine best scoring roster for passed in roster makeup and weights."""
    #TODO this goalie/IR could probably go somewhere else
    avail_players = team[(team.position_type == 'P') & (['IR' not in l for l in team.eligible_positions.values.tolist()])]
    avail_players.loc[:,'fpts'] = avail_players[list(stats_weights.index.values)].mul(stats_weights).sum(1)
    roster = tuple([RosterPlayer(id, p['eligible_positions'],p['fpts']) for id, p in avail_players.iterrows()])
    
    defensemen = [p for p in roster if p.eligible_positions == ['D']]
    
    pass

def remove_ir(team):
    """Remove IR players from dataframe."""
    return team[['IR' not in l for l in team.eligible_positions.values.tolist()]]

def remove_goalies(team):
    return team[team.position_type == 'P']


"""default roster builder."""
roster_builder = RecursiveRosterBuilder()

"""This should be used to build rosters."""
best_roster = roster_builder.find_best1


if __name__ == "__main__":

    my_team = pd.read_csv('../tests/my-team.csv',
                      converters={"eligible_positions": lambda x: x.strip("[]").replace("'", "").split(", ")})
    my_team.set_index('player_id', inplace=True)

    pass


