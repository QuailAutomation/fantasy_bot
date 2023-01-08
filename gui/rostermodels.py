

from collections import defaultdict

from multiprocessing.sharedctypes import Value
from operator import and_

from PyQt5 import QtCore

def extract_yahoo_id(yahoo_key):
        return int(yahoo_key.split('.')[-1])

Qt = QtCore.Qt

nfl_player_positions = ['QB', 'WR', 'RB', 'TE', 'K', 'DEF']

class RosterSlot:
    def __init__(self, code, valid_positions=None) -> None:
        if not valid_positions and code not in nfl_player_positions:
            raise ValueError(f"name is invalid, must be one of: {nfl_player_positions}")

        self.code = code
        # what positional players are allowed to be assigned to this slot
        self.valid_positions = []
        # holds the id of the player assigned to this slot

        if not valid_positions:
            self.valid_positions = []
            self.valid_positions.append(code)
        else:
            self.valid_positions = valid_positions
        
    def is_valid_position(self, position):
        return position in self.valid_positions

    def __hash__(self) -> int:
        return id(self)

    def __repr__(self) -> str:
        return f"RosterSlot-> Code: {self.code}, valid positions: {self.valid_positions}"
    
# RS_QB = RosterSlot('QB')
# RS_WR = RosterSlot('WR')
# RS_RB = RosterSlot('RB')
# RS_TE = RosterSlot('TE')
# RS_Flex = RosterSlot('Flex', valid_positions=['WR', 'RB', 'TE'])
# RS_K = RosterSlot('K')
# RS_D = RosterSlot('DEF')
# RS_Bench = RosterSlot('Bench', valid_positions=['QB', 'WR', 'RB', 'TE', 'K', 'DEF'])


class Roster:
    def __init__(self, roster_slots):
        self.roster_slots = roster_slots
        self.player_map = {slot:None for slot in roster_slots}

    def __len__(self) -> int:
        return len(self.roster_slots)

    def position_code(self, index):
        return self.roster_slots[index].code

    def player_at(self, index):
        return self.player_map[self.roster_slots[index]]

    def _find_next_position_index(self, position) -> int:
        for index, slot in enumerate(self.roster_slots):
            posn_ok = slot.is_valid_position(position)
            pid_in_slot = self.player_map[slot]
            print(f"Slot: {slot} -> Position ok: {posn_ok}, player in slot: {pid_in_slot}")
            if posn_ok and pid_in_slot is None:
                return index
        return None

    def insert_player(self, id, position):
        if isinstance(position, str):
            valid_insert_location = self._find_next_position_index(position)
        elif isinstance(position, list):
            for item in position:
                valid_insert_location = self._find_next_position_index(item)
                if valid_insert_location:
                    break

        if valid_insert_location is not None:
            self.player_map[self.roster_slots[valid_insert_location]] = id
        else:
            print("Unable to insert player to roster")
            print(f"Player map: {self.player_map}")
            raise ValueError(f"{position} is not able to be inserted to roster")



default_nfl_fantasy_roster = [RosterSlot('QB'), 
                            RosterSlot('WR'), RosterSlot('WR'), 
                            RosterSlot('RB'), RosterSlot('RB'), 
                            RosterSlot('TE'), RosterSlot('Flex', valid_positions=['WR', 'RB', 'TE']), 
                            RosterSlot('K'), RosterSlot('DEF'),
                            RosterSlot('Bench', valid_positions=['QB', 'WR', 'RB', 'TE', 'K', 'DEF']),
                            RosterSlot('Bench', valid_positions=['QB', 'WR', 'RB', 'TE', 'K', 'DEF']),
                            RosterSlot('Bench', valid_positions=['QB', 'WR', 'RB', 'TE', 'K', 'DEF']),
                            RosterSlot('Bench', valid_positions=['QB', 'WR', 'RB', 'TE', 'K', 'DEF']),
                            RosterSlot('Bench', valid_positions=['QB', 'WR', 'RB', 'TE', 'K', 'DEF']),
                            RosterSlot('Bench', valid_positions=['QB', 'WR', 'RB', 'TE', 'K', 'DEF']),
                            RosterSlot('Bench', valid_positions=['QB', 'WR', 'RB', 'TE', 'K', 'DEF'])]

class NFLDraftedRosterModel(QtCore.QAbstractTableModel):
    def __init__(self, data, team_key, player_projections, parent=None, keepers=None, roster_positions=default_nfl_fantasy_roster):
        QtCore.QAbstractTableModel.__init__(self, parent)
        self.draft_list = data
        # self.team_roster = []
        self.roster_makeup = Roster(default_nfl_fantasy_roster)
        # self.roster_length = len(self.roster_makeup)
        self.team_key = team_key
        self.player_projections = player_projections.set_index('player_id')
        self.league_keepers = keepers
        self.specify_team_key(team_key)

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid():
            if role == Qt.DisplayRole:
                if index.column() == 0:
                    return self.roster_makeup.position_code(index.row())
                elif index.column() == 1:
                    try:
                        player_id = self.roster_makeup.player_at(index.row())
                        return str(self.player_projections.loc[player_id]['name'])
                    except KeyError:
                        return ""
                else:
                    try:
                        player_id = self.roster_makeup.player_at(index.row())
                        return str(self.player_projections.loc[player_id]['position'])
                    except KeyError:
                        return ""
    
    def rowCount(self, parent=None):
        return len(self.roster_makeup)

    def columnCount(self, parent=None):
        return 3
    
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        return None
        # if role == Qt.DisplayRole and orientation == Qt.Horizontal:
        #     return self._column_header_list[section]
        # return QtCore.QAbstractTableModel.headerData(self, section, orientation, role)

    def player_drafted(self, draft_entry):
        print(f"TODO handle player drafted: {draft_entry}")
        if draft_entry['team_key'] == self.team_key:
            player_id = extract_yahoo_id(draft_entry['player_key'])
            try:
                player_position = self.player_projections.loc[player_id]['position']
                name = self.player_projections.loc[player_id]['name']
                print(f"player drafted: {name}, position is: {player_position}, type: {type(player_position)}")
                self.roster_makeup.insert_player(player_id, player_position)
                self.modelReset.emit()
            except KeyError:
                print(f'Player id: {player_id} not found in projections')
            
        # if our team key matches add to our list
    
    def _player_id_for_name_team(self, name, team):
        # self.projections_df.loc[self.projections_df.name.str.contains(keeper['name']) & 
        #                                 (self.projections_df.team == keeper['team']), 'draft_fantasy_key'] = team
        matching = None
        if '' != team: 
            matching =  self.player_projections.index[self.player_projections.name.str.contains(name) & (self.player_projections.team == team)].tolist()
        else:
            matching =  self.player_projections.index[self.player_projections.name.str.contains(name)].tolist()

        # assert len(matching) == 1,f"Expecting 1 and only 1 match {len(matching)}, name: {name}, team: {team}"
        if len(matching) == 1:
            return matching[0]
        else: 
            return f"{name}-{team}"

    def specify_team_key(self, team_key):
        self.team_key = team_key
        self.roster_makeup = Roster(default_nfl_fantasy_roster)
        if self.league_keepers:
            print("Must add keepers to roster")
            my_keepers = self.league_keepers[team_key]
            for keeper in my_keepers:
                self.roster_makeup.insert_player(self._player_id_for_name_team(keeper['name'], keeper.get('team', '').upper()), keeper['position'])
            pass
        # now add drafted players
        for entry in self.draft_list: 
            if entry['team_key'] == team_key:
                self.player_drafted(entry)
        self.modelReset.emit()