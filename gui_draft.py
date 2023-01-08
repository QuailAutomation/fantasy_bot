# this is draft board gui
import os
import sys
import time
import pandas as pd 
import pickle

from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import QApplication, QComboBox, QLabel, QTableView, QTableWidget, QWidget, QPushButton, QHBoxLayout, QGroupBox, QDialog, QVBoxLayout, QGridLayout, QCheckBox, QListWidget, QTableWidgetItem, QLineEdit, QFormLayout, QMenuBar, QMainWindow, QAction
from PyQt5.QtGui import QIcon, QBrush
from PyQt5.QtCore import pyqtSlot, QCoreApplication, QRunnable, QThreadPool, QIdentityProxyModel
from yahoo_fantasy_api import league
from csh_fantasy_bot.bot import ManagerBot
from csh_fantasy_bot.yahoo_projections import retrieve_yahoo_rest_of_season_projections, produce_csh_ranking
from csh_fantasy_bot.projections.yahoo_nfl import generate_predictions, PredictionType, retrieve_draft_order
from csh_fantasy_bot.projections.fantasypros_nfl import get_projections

from csh_fantasy_bot.draft import generate_snake_draft_picks

from gui.rostermodels import NFLDraftedRosterModel

import yahoo_fantasy_api as yfa
from yahoo_oauth import OAuth2

Qt = QtCore.Qt

def extract_yahoo_id(yahoo_key):
        return int(yahoo_key.split('.')[-1])

class DraftMonitor(QRunnable):
    def __init__(self, league, keepers=None) -> None:
        print(f"creating draft monitor for: {league}")
        super(DraftMonitor, self).__init__()
        self.league=league
        self._draft_listener=None
        self.draft_status = league.settings()['draft_status']
        self.drafted_players=[]
        self.last_notified_draft_index = None
        self.paused=False
        self.stop_flag = False
        # list which holds which picks were used for keepers
        self.keeper_pick_numbers = []
        if keepers:
            for _, team_keepers in keepers.items():
                for keeper_draft in team_keepers:
                    self.keeper_pick_numbers.append(keeper_draft['number'])
    
    def toggle_paused(self):
        self.paused = not self.paused
        print(f"Draft status listener is {self._draft_listener}")
        if self._draft_listener:
            self._draft_listener.draft_status_changed(self.paused) 

    def status(self):
        return self.draft_status

    def register_draft_listener(self, listener):
        self._draft_listener = listener

    def run(self):
        print("Starting draft monitor")
        if self.draft_status == 'postdraft':
            # draft is complete, lets simulate
            self._simulate_post_draft()
        else:
            self._poll_draft_results()

    def _simulate_post_draft(self):
        print("Draft is complete, switch to simulation mode")
        draft_results = self.league.draft_results()
        if len(draft_results) > 0:
            for document in draft_results:
                while True:
                    if self.stop_flag:
                        break
                    if not self.paused:
                        if document['pick'] not in self.keeper_pick_numbers:
                            self._draft_listener.player_drafted(document)
                            time.sleep(3)
                        break
                    else:
                        print("Waiting until paused changed false")
                        while True:
                            time.sleep(3)
                            if not self.paused:
                                print("paused not false")
                                break
            print("Done simulating draft")

    def _poll_draft_results(self):
        while True:
            print("Checking for draft results(Draft Monitor)")
            if self.stop_flag:
                break
            draft_results = self.league.draft_results()
            if len(draft_results) > 0:
                for document in draft_results:
                    player_id = int(document['player_key'].split('.')[-1])
                    if player_id not in self.drafted_players:
                        self.drafted_players.append(player_id)
                        self._draft_listener.player_drafted(document)

            time.sleep(30)
            
class DraftedRosterModel(QtCore.QAbstractTableModel):
    def __init__(self, data, team_key, player_projections, parent=None, keepers=None):
        QtCore.QAbstractTableModel.__init__(self, parent)
        self.draft_list = data
        self.team_roster = []
        self.team_key = team_key
        self.player_projections = player_projections.set_index('player_id')
        self.league_keepers = keepers
        self.specify_team_key(team_key)

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
        # print(f"TODO handle player drafted: {draft_entry}")
        if draft_entry['team_key'] == self.team_key:
            self.team_roster.append(extract_yahoo_id(draft_entry['player_key']))
            self.modelReset.emit()
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
        self.team_roster = []
        if self.league_keepers:
            print("Must add keepers to roster")
            my_keepers = self.league_keepers[team_key]
            for keeper in my_keepers:
                self.team_roster.append(self._player_id_for_name_team(keeper['name'], keeper.get('team', '').upper()))
            pass
        # now add drafted players
        for entry in self.draft_list:
            if entry['team_key'] == team_key:
                self.team_roster.append(extract_yahoo_id(entry['player_key']))
        self.modelReset.emit()

class PandasModel(QtCore.QAbstractTableModel):
    BG_DRAFTED = QtGui.QColor(215,214,213)
    def __init__(self, data, parent=None, column_headers=None, valid_positions=('C', 'LW', 'RW', 'D'), highlight_personal_ranking_differences=True):
        QtCore.QAbstractTableModel.__init__(self, parent)
        self._data = data
        # this will reflect what we want to see with filtering.  speeds up rendering in data func
        self.current_data_view = self._data
        self._column_headers = column_headers
        # build list which maps column headers to a column index in the dataframe
        self._columnheader_mapping =  [data.columns.get_loc(key) for key in column_headers.keys()]
        # some special columns for render optimization
        self.drafted_team_id_column = data.columns.get_loc('draft_fantasy_key')
        self.rank_playerid_col_index =  data.columns.get_loc('player_id')   
        self.highlight_personal_ranking_differences = highlight_personal_ranking_differences
        if highlight_personal_ranking_differences:
            self.rank_diff_col_index =  data.columns.get_loc('rank_diff')   
            self.csh_rank_col_index = list(column_headers.keys()).index('csh_rank')   
            self.drafted_team_id_column
        self._num_cols = len(column_headers)
        self._num_rows = len(self._data.index)
        self._column_header_list = list(self._column_headers.values())
        self._drafted_players = list()
        self.show_drafted = True
        self.positions_to_show = valid_positions
        self.sort_info = None

    def sort(self, column: int, order: Qt.SortOrder) -> None:
        self.sort_info = column, order
        sort_direction = "Ascending" if order == Qt.SortOrder.AscendingOrder else "Descending"
        print(f"Sort column: {self._column_header_list[column]}, {sort_direction}")
        self.current_data_view.sort_values(self.current_data_view.columns[self._columnheader_mapping[column]], ascending=order == Qt.SortOrder.AscendingOrder, inplace=True, ignore_index=True)
        self.modelReset.emit()
        return super().sort(column, order=order)

    def do_sort(self):
        if self.sort_info:
            self.current_data_view.sort_values(self.current_data_view.columns[self._columnheader_mapping[self.sort_info[0]]], ascending=self.sort_info[1] == Qt.SortOrder.AscendingOrder, inplace=True, ignore_index=True)
            self.modelReset.emit()
        

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
                # draft_fantasy_key
                # if int(player_data.iloc[index.row(),self.rank_playerid_col_index]) in self._drafted_players:
                if player_data.iloc[index.row(),self.drafted_team_id_column] !=  -1:
                    return QtCore.QVariant(QtGui.QColor(PandasModel.BG_DRAFTED))
                elif self.highlight_personal_ranking_differences and (index.column() == self.csh_rank_col_index):
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
        # print(f"Player drafted: {player_id}, team:{team_id}")
        self._drafted_players.append(player_id)
        self._data.loc[self._data.player_id == player_id, 'draft_fantasy_key'] = team_id
        self.apply_filters()
        self.do_sort()
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
            self.current_data_view=self._data[(self._data.draft_fantasy_key == -1) & valid_by_position]
        else:
            self.current_data_view=self._data[valid_by_position]

        self._num_rows = len(self.current_data_view.index)
        self.do_sort()
        self.modelReset.emit()


class App(QMainWindow):
    game_filter_positions = {"nhl":['C', 'LW', 'RW', 'D'], "nfl":['QB', 'RB', 'WR', 'TE', 'K', 'DEF']}
    game_projection_columns = {"nhl":{'name':'Name','posn_display':'POS', 'team':'Team', 'csh_rank':'CSH', 'preseason_rank':'Preseason', 'current_rank':'Current', 'GP':'GP','fantasy_score':'Score'} ,
                                "nfl":{'name':'Name','posn_display':'POS', 'team':'Team', 'Bye':'Bye','fan_points':'fan_points', 'overall_rank':'Rank', 'fp_rank':'FP_rank', 'position_rank':'FP_Pos'}}
    # ['name', 'position', 'player_id', 'GP', 'Bye', 'fan_points',
    #    'overall_rank', 'percent_rostered', 'pass_yds', 'pass_td', 'pass_int',
    #    'pass_sack', 'rush_attempts', 'rush_yards', 'rush_tds',
    #    'receiving_targets', 'receiving_receptions', 'receiving_yards',
    #    'receiving_tds', 'team']
    def __init__(self):
        super().__init__()
        self.title = "Yahoo Draft Board"
        self.left = 10
        self.top = 10
        self.width = 3200
        self.height = 1000
        self.main_widget = QWidget(self)
        self.oauth = OAuth2(None, None, from_file='oauth2.json')
        league_id = "403.l.41177"
        self.game_type = "nhl"
        self.game_year =2020
        self.league = None
        self.setup_menubar()
        self.my_draft_picks = None
        self.label_num_picks_before_pick = QLabel("Number picks until your turn: 4")
        self.positional_filter_checkboxes = None
        # runnable to grab draft picks from yahoo
        self.draft_monitor = None
        self.draft_complete = False
        self.draft_results = []
        self.position_filtering_layout = QHBoxLayout()
        self.draft_list_widget = QListWidget()
        self.projection_table = QTableView()
        self.projection_table.setSortingEnabled(True)

        self.pause_draft_button = QPushButton("Pause")
        self.pause_draft_button.clicked.connect(self.pause_pressed)
        
        self.team_combo_box = QComboBox()
        self.draft_status_label = QLabel("Status: Running")
        
        self.roster_table = QTableView()
        self.roster_table_model = None
        
        # self.league_changed("403.l.41177", "nhl", 2021)
        self.league_changed("406.l.246660", "nfl", 2021)
        self.initUI()

    def setup_menubar(self):
        menuBar = QMenuBar(self)
        menuBar.setNativeMenuBar(False)
        self.setMenuBar(menuBar)
        leagueMenu = menuBar.addMenu("&League")
        years = [2022, 2021, 2020, 2019,2018]
        fantasy_games = ['nhl', 'nfl']
        
        for year in years:
            year_menu = leagueMenu.addMenu(str(year))
            for game in fantasy_games:
                game_menu = year_menu.addMenu(game)
                gm = yfa.Game(self.oauth, game)
                ids = gm.league_ids(year)
                for id in ids:
                    lg = gm.to_league(id)
                    lg_action = QAction(lg.settings()['name'], self)
                    lg_action.league_id = id
                    lg_action.game_type = game
                    lg_action.year = year
                    game_menu.addAction(lg_action)
                    game_menu.triggered[QAction].connect(self.league_selected)

    def league_selected(self, q):  
        print("league selected") 
        if not (q.league_id == self.league_id and q.year == self.game_year):
            self.league_changed(q.league_id, q.game_type, q.year)

    def get_scraped_draft_results(self):
        scraped_draft_results = None
        draft_scrape_filename = f".cache/gui_draft/draft-scrape-{self.league_id}-{self.game_type}-{self.game_year}.pkl"
        if os.path.exists(draft_scrape_filename):
            with open(draft_scrape_filename, "rb") as f:
                scraped_draft_results = pickle.load(f)
        else:
            scraped_draft_results = retrieve_draft_order(self.league)
            with open(draft_scrape_filename, "wb") as f:
                pickle.dump(scraped_draft_results, f)
        return scraped_draft_results

    def league_changed(self, league_id, game_type, year):
        print(f"League changed, id: {league_id} - type: {game_type} - year:{year}")
        if self.draft_monitor is not None and self.league_id != league_id:
            self.draft_monitor.stop_flag = True
            print("Draft thread cancelled")
        self.league_id = league_id
        self.game_type = game_type
        self.game_year = year
        self.league = yfa.league.League(self.oauth, self.league_id)
        self.my_draft_picks = self._get_draft_picks(self.league.team_key())
        
        self.projections_df = self.retrieve_player_projections()
        
        # figure out if we have keepers
        scraped_draft_results = None
        if "nfl" == self.game_type:
            # for keeper leagues, would be defined in a screen scrape.  lets do that and simulate them
            scraped_draft_results = self.get_scraped_draft_results()
                
            # assign keepers to teams
            for team, keepers in scraped_draft_results['keepers'].items():
                for keeper in keepers:
                    if 'team' in keeper.keys():
                        self.projections_df.loc[self.projections_df.name.str.contains(keeper['name']) & 
                                    (self.projections_df.team == keeper['team'].upper()), ['draft_fantasy_key','is_keeper']] = team, True
                    else:
                        self.projections_df.loc[self.projections_df.name.str.contains(keeper['name']), ['draft_fantasy_key','is_keeper']] = team, True
       
        base_columns = App.game_projection_columns[self.game_type].copy()
        # add league specifc scoring cats for hockey
        if self.game_type == "nhl":
            for stat in self.league.stat_categories():
                if stat['position_type'] == 'P':
                    base_columns[stat['display_name']] = stat['display_name']
        self.projections_model = PandasModel(self.projections_df , column_headers=base_columns,
                                            valid_positions=App.game_filter_positions[self.game_type],
                                            highlight_personal_ranking_differences=self.game_type=="nhl")

        self.team_name_by_id = {team['team_key']:team['name'] for team in self.league.teams()}
        self.team_key_by_name = {team['name']:team['team_key'] for team in self.league.teams()}
        
        self.build_filter_panel()
        
        self.projections_model.update_filters(self._position_filter_list())
        
        self.draft_complete = False
        self.draft_results = []
    
        self.projection_table.setModel(self.projections_model)
        self.pause_draft_button = QPushButton("Pause")
        self.pause_draft_button.clicked.connect(self.pause_pressed)
        
        self.team_combo_box.clear()
        for team in self.league.teams():
            self.team_combo_box.addItem(team['name'], team['team_key'])
        self.team_combo_box.setCurrentIndex(self.team_combo_box.findData(self.league.team_key()))
        print(f'game type: {self.game_type}')
        if self.game_type == "nfl":
            self.roster_table_model = NFLDraftedRosterModel(self.draft_results, self.league.team_key(), self.projections_df, 
                                    keepers=scraped_draft_results['keepers'] if scraped_draft_results else None)                                
        else:                                    
            self.roster_table_model = DraftedRosterModel(self.draft_results, self.league.team_key(), self.projections_df, 
                                    keepers=scraped_draft_results['keepers'] if scraped_draft_results else None)

        self.roster_table.setModel(self.roster_table_model)

        self.draft_list_widget.clear()
        self.update_picks_until_next_player_pick(0)
        the_keepers = scraped_draft_results.get('keepers', None) if scraped_draft_results else None
        self.draft_monitor = DraftMonitor(self.league, keepers=the_keepers)
        self.draft_monitor.register_draft_listener(self)
        QThreadPool.globalInstance().start(self.draft_monitor)

    
    def build_filter_panel(self):
        '''
        builds the position checkbox filters
        depends on game_type
        '''
        # clear any checkboxes
        for i in reversed (range(self.position_filtering_layout.count())):
            self.position_filtering_layout.itemAt(i).widget().close()
            self.position_filtering_layout.takeAt(i)
        self.positional_filter_checkboxes = []
        for position in self.game_filter_positions[self.game_type]:
            box = QCheckBox(position)
            box.setChecked(True)
            box.clicked.connect(self.filter_checked)
            self.positional_filter_checkboxes.append(box)
            self.position_filtering_layout.addWidget(box)
        
        all_button = QPushButton('All')
        all_button.pressed.connect(self.filter_all_selected)
        self.position_filtering_layout.addWidget(all_button)
        none_button = QPushButton('None')
        none_button.pressed.connect(self.filter_none_selected)
        self.position_filtering_layout.addWidget(none_button)
        
    
    def retrieve_player_projections(self):
        projections = None
        if "nhl" == self.game_type:
            projections = retrieve_yahoo_rest_of_season_projections(self.league.league_id)
            scoring_stats = [stat['display_name'] for stat in self.league.stat_categories() if stat['position_type'] == 'P']
            produce_csh_ranking(projections, scoring_stats, 
                        projections.index, ranking_column_name='fantasy_score')
            projections['fantasy_score'] = round(projections['fantasy_score'], 3)
            projections.reset_index(inplace=True)
            projections.sort_values("fantasy_score", ascending=False, inplace=True, ignore_index=True)
            projections['csh_rank'] = projections.index + 1
            
            projections['rank_diff'] = projections['csh_rank'] - projections['current_rank']
        else:
            projections = pd.read_csv(f"{self.game_year}-{self.league_id}-predictions-merged.csv", converters={"position": lambda x: x.strip("[]").replace('"', "").replace("'", "").replace(" ", "").split(",")})
            sort_col = 'preseason'
            if 'overall_rank' in projections.columns:
                sort_col = 'overall_rank'
            projections.sort_values(sort_col, inplace=True)
            
        
        projections['draft_fantasy_key'] = -1
        projections['is_keeper'] = False
        # use this for rendering eligible positions
        projections ['posn_display']  = projections ['position'].apply(lambda x: ", ".join(x))
        
        return projections

    def draft_status_changed(self, is_paused):
        self.draft_status_label.setText("Status: Paused" if is_paused else "Status: Running")
        
    def _get_draft_picks(self, team_key):
        scraped = self.get_scraped_draft_results()
        if 'predraft' == scraped['status']:
            return scraped['draft_picks'].get('team_key', [])
        else:
            return [int(key['number']) for key in scraped['draft_picks'][team_key]]

    def initUI(self):
        self.setWindowTitle(self.title)
        self.setCentralWidget(self.main_widget)
        self.layout_screen()
        self.show()

    def pause_pressed(self):
        print("Pause pressed")
        if self.draft_monitor:
            self.draft_monitor.toggle_paused()
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
    
    def _position_filter_list(self):
        return {checkbox.text() for checkbox in self.positional_filter_checkboxes if checkbox.isChecked()}

    def filter_all_selected(self):
        print("All button pressed")
        for checkbox in self.positional_filter_checkboxes:
            checkbox.setChecked(True)
        self.projections_model.update_filters(self._position_filter_list())

    def filter_none_selected(self):
        print("None pressed")
        for checkbox in self.positional_filter_checkboxes:
            checkbox.setChecked(False)
        self.projections_model.update_filters(self._position_filter_list())

    def filter_checked(self, state):
        print(f"filter was checked: {self.sender().text()}")
        self.projections_model.update_filters(self._position_filter_list())

    def layout_screen(self):

        layout = QHBoxLayout()
        left_layout = QVBoxLayout()
        
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
        
        filtering_layout.addLayout(self.position_filtering_layout)
        filtering_layout.addLayout(second_filter_layout)
        second_filter_layout.addStretch(1)

        # this displays list of eligible players, and their projections
        self._set_projection_table_widths(self.projection_table)
        projection_layout = QVBoxLayout()
        
        projection_layout.addWidget(self.projection_table)
        # projection_layout.addWidget(QTableView())

        roster_layout = QVBoxLayout()
        roster_layout.addWidget(self.draft_status_label)
        roster_team_selection = QHBoxLayout()
        
        # set up draft pause button
        roster_team_selection.addWidget(self.pause_draft_button)

        roster_team_selection.addWidget(QLabel("Team: "))

        self.team_combo_box.view().pressed.connect(self.handle_team_roster_changed)
        roster_team_selection.addWidget(self.team_combo_box)

        roster_layout.addLayout(roster_team_selection)
        
        game_selection_layout = QHBoxLayout()
        game_selection_layout.addWidget(self.label_num_picks_before_pick)
        game_selection_layout.addStretch(1)

        roster_layout.addWidget(self.roster_table)
        roster_layout.addWidget(self.draft_list_widget)

        left_layout.addLayout(game_selection_layout)
        
        left_layout.addLayout(filtering_layout)
        left_layout.addLayout(projection_layout)
        layout.addLayout(left_layout, stretch=2)
        layout.addLayout(roster_layout)
        self.main_widget.setLayout(layout)


    def player_drafted(self, draft_entry):
        self.draft_results.append(draft_entry)
        print(f"de: {draft_entry}")
        player_id = int(draft_entry['player_key'].split('.')[-1])
        draft_position = int(draft_entry['pick'])
        player_name = None
        draft_value = 'n/a'
        try:
            player_name = self.projections_df[self.projections_df.player_id == player_id]['name'].values[0]
            # figure out draft position relative to csh_rank ranking
            try:
                csh_rank = self.projections_df[self.projections_df.player_id == player_id]['csh_rank'].values[0]
                draft_value = draft_position - csh_rank 
            except KeyError:
                pass
        except IndexError:
            player_name = f"Unknown({player_id})"

        team_id = int(draft_entry['team_key'].split('.')[-1])
        self.projections_model.player_drafted(player_id, team_id)
        self.roster_table_model.player_drafted(draft_entry)
        try:
            next_draft = next(x for x in self.my_draft_picks if x > draft_position)
            self.label_num_picks_before_pick.setText(f"Number picks until your turn: {next_draft-draft_position}")        
        except StopIteration:
            pass
        self.draft_list_widget.insertItem(0, f"{draft_position}. {player_name} - {self.team_name_by_id[draft_entry['team_key']]} - ({draft_value})")
    
    def update_picks_until_next_player_pick(self, current_draft_position):
        try:
            next_draft = next(x for x in self.my_draft_picks if x > current_draft_position)
            self.label_num_picks_before_pick.setText(f"Number picks until your turn: {next_draft-current_draft_position}")
        except StopIteration:
            pass
    

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = App()
    # runnable = DraftMonitor(ex.league)
    # runnable.register_draft_listener(ex)
    # runnable.register_status_listener(ex)

    # QThreadPool.globalInstance().start(runnable)
    sys.exit(app.exec_())