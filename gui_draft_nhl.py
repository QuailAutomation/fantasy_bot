# this is draft board gui

import sys
import time

from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import QApplication, QComboBox, QLabel, QTableView, QTableWidget, QWidget, QPushButton, QHBoxLayout, QGroupBox, QDialog, QVBoxLayout, QGridLayout, QCheckBox, QListWidget, QTableWidgetItem, QLineEdit, QFormLayout
from PyQt5.QtGui import QIcon, QBrush
from PyQt5.QtCore import pyqtSlot, QCoreApplication, QRunnable, QThreadPool, QIdentityProxyModel
from csh_fantasy_bot.bot import ManagerBot
from csh_fantasy_bot.yahoo_projections import retrieve_yahoo_rest_of_season_projections, produce_csh_ranking
from csh_fantasy_bot.draft import generate_snake_draft_picks
Qt = QtCore.Qt

def extract_yahoo_id(yahoo_key):
        return int(yahoo_key.split('.')[-1])

class DraftMonitor(QRunnable):
    def __init__(self, league) -> None:
        super(DraftMonitor, self).__init__()
        self.league = league
        self._draft_listener=None
        self.draft_status_listener=None
        self.draft_status = league.settings()['draft_status']
        self.drafted_players=[]
        self.last_notified_draft_index = None
        self.paused=False
    
    def toggle_paused(self):
        self.paused = not self.paused
        print(f"Draft status listener is {self.draft_status_listener}")
        if self.draft_status_listener:
            self.draft_status_listener.draft_status_changed(self.paused) 

    def status(self):
        return self.draft_status
    
    """ Step through draft in simulation mode """
    def step(steps=1):
        assert False, "Not implemented"

    def register_status_listener(self, listener):
        self.draft_status_listener = listener

    def register_draft_listener(self, listener):
        self._draft_listener = listener
        listener.register_draft_supplier(self)

    def run(self):
        if self.draft_status == 'postdraft':
            # draft is complete, lets simulate
            print("Draft is complete, switch to simulation mode")
            draft_results = self.league.draft_results()
            if len(draft_results) > 0:
                for document in draft_results:
                    while True:
                        if not self.paused:
                            self._draft_listener.player_drafted(document)
                            time.sleep(3)
                            break
                        else:
                            print("Waiting until paused changed false")
                            while True:
                                time.sleep(1)
                                if not self.paused:
                                    print("paused not false")
                                    break
                print("Done simulating draft")
        else:
            while True:
                print("Checking for draft results(Draft Monitor)")
                draft_results = self.league.draft_results()
                if len(draft_results) > 0:
                    for document in draft_results:
                        player_id = int(document['player_key'].split('.')[-1])
                        if player_id not in self.drafted_players:
                            self.drafted_players.append(player_id)
                            self._draft_listener.player_drafted(int(player_id))

                time.sleep(30)
            
class DraftedRosterModel(QtCore.QAbstractTableModel):
    def __init__(self, data, team_key, player_projections, parent=None):
        QtCore.QAbstractTableModel.__init__(self, parent)
        self.draft_list = data
        self.team_roster = [entry['player_id'] for entry in data if entry['team_key'] == team_key]
        self.team_key = team_key
        self.player_projections = player_projections.set_index('player_id')

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid():
            if role == Qt.DisplayRole and index.row() < len(self.team_roster):
                try:
                    return str(self.player_projections.loc[self.team_roster[index.row()]]['name'])
                except KeyError:
                    return "Unavailable(probably G)"
    
    def rowCount(self, parent=None):
        return 16

    def columnCount(self, parent=None):
        return 1
    
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        return None
        # if role == Qt.DisplayRole and orientation == Qt.Horizontal:
        #     return self._column_header_list[section]
        # return QtCore.QAbstractTableModel.headerData(self, section, orientation, role)

    def player_drafted(self, draft_entry):
        print(f"TODO handle player drafted: {draft_entry}")
        if draft_entry['team_key'] == self.team_key:
            self.team_roster.append(extract_yahoo_id(draft_entry['player_key']))
            self.modelReset.emit()
        # if our team key matches add to our list
        
    def specify_team_key(self, team_key):
        self.team_key = team_key
        self.team_roster = [extract_yahoo_id(entry['player_key']) for entry in self.draft_list if entry['team_key'] == team_key]
        self.modelReset.emit()

class PandasModel(QtCore.QAbstractTableModel):
    BG_DRAFTED = QtGui.QColor(215,214,213)
    def __init__(self, data, parent=None, column_headers=None):
        QtCore.QAbstractTableModel.__init__(self, parent)
        self._data = data
        # this will reflect what we want to see with filtering.  speeds up rendering in data func
        self.current_data_view = self._data
        self._column_headers = column_headers
        # build list which maps column headers to a column index in the dataframe
        self._columnheader_mapping =  [data.columns.get_loc(key) for key in column_headers.keys()]
        self._data['rank_diff'] = self._data['csh_rank'] - self._data['current_rank']
        # some special columns for render optimization
        self.rank_playerid_col_index =  data.columns.get_loc('player_id')   
        self.rank_diff_col_index =  data.columns.get_loc('rank_diff')   
        self.csh_rank_col_index = list(column_headers.keys()).index('csh_rank')   
        self._num_cols = len(column_headers)
        self._num_rows = len(self._data.index)
        self._column_header_list = list(self._column_headers.values())
        self._drafted_players = list()
        self.show_drafted = True
        self.positions_to_show = {'C', 'LW', 'RW', 'D'}

    def rowCount(self, parent=None):
        return self._num_rows

    def columnCount(self, parent=None):
        return self._num_cols

    def data(self, index, role=Qt.DisplayRole):
        #TODO shold demarcate my draft positions
        if index.isValid():
            player_data = self.current_data_view
            if role == Qt.DisplayRole:
                return str(player_data.iloc[index.row(),self._columnheader_mapping[index.column()]])
            elif role == QtCore.Qt.BackgroundRole:
                if int(player_data.iloc[index.row(),self.rank_playerid_col_index]) in self._drafted_players:
                    return QtCore.QVariant(QtGui.QColor(PandasModel.BG_DRAFTED))
                elif (index.column() == self.csh_rank_col_index):
                    if (player_data.iloc[index.row(),self.rank_diff_col_index] < -10):
                        return QtCore.QVariant(QtGui.QColor(QtCore.Qt.green))
                    elif (player_data.iloc[index.row(),self.rank_diff_col_index] > 10):
                        return QtCore.QVariant(QtGui.QColor(QtCore.Qt.red))
            # elif role == QtCore.Qt.FontRole and int(self._data.iloc[index.row(),self.rank_playerid_col_index]) in self._drafted_players:
            #     font = QtGui.QFont()
            #     font.setStrikeOut(True)
            #     return QtCore.QVariant(font)
            elif role == QtCore.Qt.TextAlignmentRole and index.column() > 0:
                return QtCore.Qt.AlignCenter
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self._column_header_list[section]
        return QtCore.QAbstractTableModel.headerData(self, section, orientation, role)

    def player_drafted(self, player_id, team_id):
        print(f"Player drafted: {player_id}, team:{team_id}")
        self._drafted_players.append(player_id)
        self._data.loc[self._data.player_id == player_id, 'draft_fantasy_key'] = team_id
        self.apply_filters()
        self.modelReset.emit()
    
    def set_hide_drafted(self, flag):
        self.show_drafted = not flag
        self.apply_filters()

    def update_filters(self, positions_to_show):
        print(f"Filters have been updated: {positions_to_show}")
        self.positions_to_show = positions_to_show
        self.apply_filters()
    
    def apply_filters(self):
        valid_by_position = ~self._data['position'].apply(lambda x: self.positions_to_show.isdisjoint(x))
        if not self.show_drafted:
            # show_drafted = self._data.draft_fantasy_key == -1
            self.current_data_view=self._data[(self._data.draft_fantasy_key == -1) & valid_by_position]
        else:
            self.current_data_view=self._data[valid_by_position]

        self._num_rows = len(self.current_data_view.index)
        self.modelReset.emit()


class App(QDialog):
    def __init__(self):
        super().__init__()
        self.title = "CSH Draft Board"
        self.left = 10
        self.top = 10
        self.width = 3200
        self.height = 1000
        self.projection_columns = {'name':'Name','posn_display':'POS', 'team':'Team', 'csh_rank':'CSH', 'preseason_rank':'Preseason', 'current_rank':'Current', 'GP':'GP','fantasy_score':'Score'} 
        
        # lg_id = "403.l.18782"
        lg_id = "403.l.41177"
        
        self.manager = ManagerBot(league_id=lg_id)
        my_team_key = self.manager.lg.team_key()

        for cat in self.manager.stat_categories:
            self.projection_columns[cat] = cat

        self.my_draft_picks = self._get_draft_picks(my_team_key)
        self.label_num_picks_before_pick = QLabel("Number picks until your turn: 4")
        self.projections_df = self.retrieve_player_projections()
        # use this for rendering eligible positions
        self.projections_df ['posn_display']  = self.projections_df ['position'].apply(lambda x: ", ".join(x))
        self.projections_model = PandasModel(self.projections_df , column_headers=self.projection_columns)

        self.team_name_by_id = {team['team_key']:team['name'] for team in self.manager.lg.teams()}
        self.team_key_by_name = {team['name']:team['team_key'] for team in self.manager.lg.teams()}
        self.positional_filter_checkboxes = {pos:QCheckBox(pos) for pos in ['C', 'LW', 'RW', 'D']}
        for checkbox in self.positional_filter_checkboxes.values():
            checkbox.setChecked(True)

        self.last_draft_count = 0
        self.draft_supplier = None
        self.draft_complete = False
        self.draft_results = []
        self.draft_list_widget = QListWidget()
        self.pause_draft_button = QPushButton("Pause")
        self.pause_draft_button.clicked.connect(self.pause_pressed)

        self.team_combo_box = QComboBox()
        self.draft_status_label = QLabel("Status: Running")
        for team in self.manager.lg.teams():
            self.team_combo_box.addItem(team['name'], team['team_key'])
        self.team_combo_box.setCurrentIndex(self.team_combo_box.findData(my_team_key))

        self.roster_table = QTableView()
        self.roster_table_model = DraftedRosterModel(self.draft_results, my_team_key, self.projections_df)
        self.roster_table.setModel(self.roster_table_model)

        self.initUI()
    
    def retrieve_player_projections(self):
        projections = retrieve_yahoo_rest_of_season_projections(self.manager.lg.league_id)
        produce_csh_ranking(projections, self.manager.stat_categories, 
                    projections.index, ranking_column_name='fantasy_score')
        projections['fantasy_score'] = round(projections['fantasy_score'], 3)
        projections.reset_index(inplace=True)
        projections.sort_values("fantasy_score", ascending=False, inplace=True, ignore_index=True)
        projections['csh_rank'] = projections.index + 1
        projections['draft_fantasy_key'] = -1
        return projections

    def draft_status_changed(self, status):
        if status:
            self.draft_status_label.setText("Status: Paused")
        else:
            self.draft_status_label.setText("Status: Running")

    def _get_draft_picks(self, team_key):
        draft_results = self.manager.lg.draft_results()
        # find first pick which matches team_key
        draft_position = None
        for draft_info in draft_results:
            if draft_info['team_key'] == team_key:
                draft_position = int(draft_info['pick'])
                assert draft_info['round'] == 1, "Didnt find team key in first round of draft"
                break
        # num teams in league
        n_teams = len(self.manager.lg.teams())
        
        #num rounds in draft
        n_rounds = int(len(draft_results)/ n_teams)

        return generate_snake_draft_picks(n_teams=n_teams, n_rounds=n_rounds, draft_position=draft_position)


    def initUI(self):
        self.setWindowTitle(self.title)
        self.layout_screen()
        self.show()

    def pause_pressed(self):
        print("Pause pressed")
        if self.draft_supplier:
            self.draft_supplier.toggle_paused()
        if "Pause" == self.pause_draft_button.text():
            self.pause_draft_button.setText("Resume")
        else:
            self.pause_draft_button.setText("Pause")
        
    def handle_team_roster_changed(self, index):
        print(f"Do something with the selected item: {index.data()}")
        self.roster_table_model.specify_team_key(self.team_key_by_name[index.data()])
        # self.roster_table.setModel(DraftedRosterModel(self.draft_results,self.team_key_by_name[index.data()]))
    
    def _set_projection_table_widths(self, table):
        table.setColumnWidth(0,140)
        table.setColumnWidth(1,60)
        table.setColumnWidth(2,60)
        table.setColumnWidth(3,50)
        table.setColumnWidth(4,50)
        table.setColumnWidth(5,50)
        table.setColumnWidth(6,50)
        table.setColumnWidth(7,60)
        table.setColumnWidth(8,50)
        table.setColumnWidth(9,50)
        table.setColumnWidth(10,50)
        table.setColumnWidth(11,50)
        table.setColumnWidth(12,50)
        table.setColumnWidth(13,50)
        table.setColumnWidth(14,50)

    def hide_drafted_click(self):
        cbutton= self.sender()
        self.projections_model.set_hide_drafted(cbutton.isChecked())
        # self.projections_model.show_drafted = not cbutton.isChecked()
        # self.projections_model.modelReset.emit()
    
    def _position_filter_list(self):
        return {posn for posn,checkbox in self.positional_filter_checkboxes.items() if checkbox.isChecked()}

    def filter_all_selected(self):
        print("All button pressed")
        for checkbox in self.positional_filter_checkboxes.values():
            checkbox.setChecked(True)
        self.projections_model.update_filters(self._position_filter_list())

    def filter_none_selected(self):
        print("None pressed")
        for checkbox in self.positional_filter_checkboxes.values():
            checkbox.setChecked(False)
        self.projections_model.update_filters(self._position_filter_list())

    def filter_checked(self, state):
        print(f"filter was checked: {self.sender().text()}")
        self.projections_model.update_filters(self._position_filter_list())

    def layout_screen(self):
        layout = QHBoxLayout()
        left_layout = QVBoxLayout()
        # filtering
        position_filtering_layout = QHBoxLayout()
        for posn, checkbox in self.positional_filter_checkboxes.items():
            checkbox.clicked.connect(self.filter_checked)
            position_filtering_layout.addWidget(checkbox)

        # position_filtering_layout.addWidget(QCheckBox('G'))
        all_button = QPushButton('All')
        all_button.pressed.connect(self.filter_all_selected)
        position_filtering_layout.addWidget(all_button)
        none_button = QPushButton('None')
        none_button.pressed.connect(self.filter_none_selected)
        position_filtering_layout.addWidget(none_button)
        
        second_filter_layout = QHBoxLayout()
        hide_drafted = QCheckBox('Hide drafted')
        hide_drafted.toggled.connect(self.hide_drafted_click)
        second_filter_layout.addWidget(hide_drafted)
        
        name_filter_layout = QFormLayout()
        name_filter_text = QLineEdit()
        name_filter_text.setMaximumWidth(400)
        name_filter_layout.addRow(QLabel("Name filter: "), name_filter_text)
        
        second_filter_layout.addLayout(name_filter_layout)
        filtering_layout = QVBoxLayout()
        filtering_layout.addLayout(position_filtering_layout)
        filtering_layout.addLayout(second_filter_layout)
        second_filter_layout.addStretch(1)

        # this displays list of eligible players, and their projections
        projection_table = QTableView()
        projection_table.setModel(self.projections_model)
        self._set_projection_table_widths(projection_table)
        projection_layout = QVBoxLayout()
        
        projection_layout.addWidget(projection_table)
        projection_layout.addWidget(QTableView())

        roster_layout = QVBoxLayout()
        roster_layout.addWidget(self.draft_status_label)
        roster_team_selection = QHBoxLayout()
        
        # set up draft pause button
        roster_team_selection.addWidget(self.pause_draft_button)

        roster_team_selection.addWidget(QLabel("Team: "))

        self.team_combo_box.view().pressed.connect(self.handle_team_roster_changed)
        roster_team_selection.addWidget(self.team_combo_box)

        roster_layout.addLayout(roster_team_selection)
        
        # this sets row headers of roster to num spots for each position
        # roster_makeup_index = 0
        # for posn, num_spots in self.manager.lg.roster_makeup().items():
        #     if posn != 'IR':
        #         for _ in range(num_spots):
        #             self.roster_table.setVerticalHeaderItem(roster_makeup_index, QTableWidgetItem(posn))
        #             roster_makeup_index += 1

        roster_layout.addWidget(self.roster_table)
        roster_layout.addWidget(self.draft_list_widget)

        left_layout.addWidget(self.label_num_picks_before_pick)
        left_layout.addLayout(filtering_layout)
        left_layout.addLayout(projection_layout)
        layout.addLayout(left_layout, stretch=2)
        layout.addLayout(roster_layout)
        self.setLayout(layout)

    def register_draft_supplier(self, draft_supplier):
        self.draft_supplier = draft_supplier

    def player_drafted(self, draft_entry):
        self.draft_results.append(draft_entry)

        player_id = int(draft_entry['player_key'].split('.')[-1])
        draft_position = int(draft_entry['pick'])
        player_name = None
        draft_value = 'n/a'
        try:
            player_name = self.projections_df[self.projections_df.player_id == player_id]['name'].values[0]
            # figure out draft position relative to csh_rank ranking
            csh_rank = self.projections_df[self.projections_df.player_id == player_id]['csh_rank'].values[0]
            draft_value = draft_position - csh_rank 
        except IndexError:
            player_name = f"Unknown({player_id})"
        team_id = int(draft_entry['team_key'].split('.')[-1])
        print(f"Player1 drafted was: {player_id}" )
        self.projections_model.player_drafted(player_id, team_id)
        self.roster_table_model.player_drafted(draft_entry)
        next_draft = next(x for x in self.my_draft_picks if x > draft_position)
        
        self.label_num_picks_before_pick.setText(f"Number picks until your turn: {next_draft-draft_position}")
        # self.my_draft_picks
        # "Number picks until your turn: 4"
        # self.label_num_picks_before_pick
        # 6743 mcdavid
        
        self.draft_list_widget.insertItem(0, f"{draft_position}. {player_name} - {self.team_name_by_id[draft_entry['team_key']]} - ({draft_value})")
    

    

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = App()
    runnable = DraftMonitor(ex.manager.lg)
    runnable.register_draft_listener(ex)
    runnable.register_status_listener(ex)

    QThreadPool.globalInstance().start(runnable)
    sys.exit(app.exec_())