#!/bin/python

import logging
import datetime
import json
import numpy as np
from collections import namedtuple
from contextlib import suppress

import cProfile, pstats, io


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

RosterChange = namedtuple('RosterChange', 'out_player_id in_player_id change_date in_projections')

class RosterChangeSet:
    def __init__(self, changes=None, max_allowed=4):
        self.max_allowed_changes = max_allowed
        self._equality_value = None
        self.score = None
        self.scoring_summary = None
        self.roster_changes = []
        self.log = logging.getLogger(__name__)
        if changes is not None:
            for change in changes:
                self.add(change)

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
        cloned_roster_changes = [RosterChange(**rc._asdict()) for rc in self.roster_changes]

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
        sorted_changes = sorted(self.roster_changes, key = lambda i: i.in_player_id,reverse=True)
        self._equality_value = "RC" + ''.join(("-".join(*i) for i in self.roster_changes))

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

    def add(self, rosterchange):
        """Add a roster change to the set."""
        if len(self.roster_changes) >= self.max_allowed_changes:
            raise RosterException("Roster change set already full")
        
        if any(True for change in self.roster_changes if change.out_player_id == rosterchange.out_player_id 
                or change.in_player_id == rosterchange.in_player_id):
            raise RosterException("Having same player in/out on multiple roster changes not supported")
           
        if isinstance(rosterchange.change_date, datetime.date):
            date_string = str(rosterchange.change_date)
        else:
            date_string = np.datetime_as_string(rosterchange.change_date, unit='D')
        # equality_score = "O{}I{}D{}".format(rosterchange.out_player_id, rosterchange.in_player_id,
        #                                     date_string)
        self.roster_changes.append(rosterchange)
        # self._compute_equality_score()
        self.score = None
            

    def replace(self, old_roster_change, new_roster_change):
        """Replace old roster change with new one."""
        if new_roster_change is not None:
            # if we are removing same player in these 2 changes, this will be valid
            try:
                if old_roster_change is not None and new_roster_change.out_player_id == old_roster_change.out_player_id:
                    pass
                elif new_roster_change.out_player_id in [rc.out_player_id for rc in self.roster_changes]:
                    raise RosterException("Having same player out on multiple roster changes not supported")
            except TypeError as e:
                self.log.exception(e)
            if (old_roster_change is not None and new_roster_change.in_player_id != old_roster_change.in_player_id) and (
                    new_roster_change.in_player_id in [rc.in_player_id for rc in self.roster_changes]):
                raise RosterException("Having same player in on multiple roster changes not supported")
        if old_roster_change is not None:
            self.roster_changes = [rc for rc in self.roster_changes if rc.out_player_id != old_roster_change.out_player_id]
            self.score = None
        if new_roster_change is not None:
            self.add(new_roster_change)
            self.score = None

    def get(self, date):
        return [change for change in self.roster_changes if change.change_date == date]

    def get_changes(self):
        return self.roster_changes

    def to_jsons(self):
        """Convert to json string."""
        return json.dumps(self.__dict__, default=lambda o: o.__dict__, 
            sort_keys=True, indent=4)

    def __str__(self):
        return_string = ""
        for rc in self.roster_changes:
            return_string += f"Out id: {rc.out_player_id}, in: {rc.in_player_id}, change date: {rc.change_date}\n"
        # return f"Number roster changes: {len(self.roster_changes)}"
        return return_string

    def pretty_print(self, score=None, projected_stats=None):
        print(f"num roster changes: {len(self.roster_changes)}")
        for rc in self.roster_changes:
            # we may be called without names avail, just ignore
            out_name = "Unknown"
            with suppress(KeyError, AttributeError):
                out_name = projected_stats.at[rc.out_player_id,'name']
            in_name = "Unknown"
            with suppress(KeyError, AttributeError):
                in_name = projected_stats.at[rc.in_player_id,'name']
            
            print(f"Date: {rc.change_date}, in: {in_name}({rc.in_player_id}), out: {out_name}({rc.out_player_id})")
        if score is not None:
            print(f"Score: {round(score,4)}")

    @classmethod
    def from_json(cls, jsons):
        """Create change set from json."""
        pass

    @classmethod
    def from_pretty_print_text(cls, roster_changes, player_df):
        """
        Date: 2021-02-06, in: Vladislav Namestnikov(5388), out: Kevin Hayes(4984)
        Date: 2021-02-04, in: Dylan Strome(6745), out: Jeff Carter(3349)
        Date: 2021-02-05, in: Alexis Lafreniere(8641), out: Darnell Nurse(5986)
        """
        rcs = RosterChangeSet()
        for rc_line in roster_changes.split('\n'):
            if rc_line != '':
                roster_change_parts = rc_line.split(',')
                change_date = datetime.datetime.strptime(roster_change_parts[0].split(':')[-1].strip(), '%Y-%m-%d').date()
                string = roster_change_parts[1]
                in_player_id = int(string[string.find("(")+1:string.find(")")])
                string = roster_change_parts[2]
                out_player_id = int(string[string.find("(")+1:string.find(")")])
                rcs.add(RosterChange(out_player_id, in_player_id, change_date, player_df.loc[in_player_id]))
            # roster_changes.append(roster_change_optimizer.RosterChange) 
        return rcs


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
