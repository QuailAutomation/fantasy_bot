# this is draft board gui

import sys
import time

from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import QApplication, QComboBox, QLabel, QTableView, QTableWidget, QWidget, QPushButton, QHBoxLayout, QGroupBox, QDialog, QVBoxLayout, QGridLayout
from PyQt5.QtGui import QIcon, QBrush
from PyQt5.QtCore import pyqtSlot, QCoreApplication, QRunnable, QThreadPool, QIdentityProxyModel
from csh_fantasy_bot.bot import ManagerBot
from csh_fantasy_bot.yahoo_projections import retrieve_yahoo_projections

Qt = QtCore.Qt

class DraftedProxy(QIdentityProxyModel):
    def data(self, index, role=Qt.DisplayRole):
        if role == QtCore.Qt.BackgroundRole:
            data = index.data()
            try:
                value = float(data)
            except (ValueError, TypeError) as e:
                print("error:", e)
            else:
                return QtCore.Qt.QColor("green") if 12 <= value <= 20 else QtCore.QtQColor("red")
        return super().data(index, role)

class PandasModel(QtCore.QAbstractTableModel):
    def __init__(self, data, parent=None, column_headers=None):
        QtCore.QAbstractTableModel.__init__(self, parent)
        self._data = data
    
        self._column_headers = column_headers
        self._num_cols = len(column_headers)
        self._column_header_list = list(self._column_headers.values())
        self._drafted_players = list()

    def rowCount(self, parent=None):
        return len(self._data.values)

    def columnCount(self, parent=None):
        return self._num_cols

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid():
            if role == Qt.DisplayRole:
                return QtCore.QVariant(str(
                    self._data.loc[index.row(),list(self._column_headers.values())[index.column()]]))
            if role == QtCore.Qt.BackgroundRole and int(self._data.loc[index.row(),['player_id']]) in self._drafted_players:
                return QtCore.QVariant(QtGui.QColor(QtCore.Qt.green))
        return QtCore.QVariant()

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self._column_header_list[section]
        return QtCore.QAbstractTableModel.headerData(self, section, orientation, role)
    
    # def setData(self, index, value):
    #     # self.__data[index.row()][index.column()] = value
    #     return True

    def player_drafted(self, player_id):
        print("IN DrAFT UPDATE")
        self._drafted_players.append(player_id)
        self.modelReset.emit()
        # self.setData(0,1)

class Runnable(QRunnable):
    
    def set_app(self, app):
        self.app = app
        self.drafted_players = []

    def set_manager(self, manager):
        self.manager = manager

    def run(self):

        
        count = 0
        app = QCoreApplication.instance()
        while True:
            print("Checking for draft results")
            draft_results = self.manager.lg.draft_results()
            if len(draft_results) > 0:
                for document in draft_results:
                    player_id = int(document['player_key'].split('.')[-1])
                    if player_id not in self.drafted_players:
                        self.drafted_players.append(player_id)
                        self.app.player_drafted(int(player_id))


            # print(f"Draft results: {draft_results}")
            # self.app.player_drafted(draft_ids[count])
            time.sleep(30)
            # count += 1
        # app.quit()

class App(QDialog):
    def __init__(self):
        super().__init__()
        self.title = "CSH Draft Board"
        self.left = 10
        self.top = 10
        self.width = 3200
        self.height = 1000
        self.projections_model = None
        self.draft_ids = [6743, 6369, 5699, 3637,7109,3737]
        self.last_draft_count = 0
        # self.projection_model = QtGui.QStandardItemModel(self)
        league_id = "403.l.18782"
        league_id = "403.l.41177"
        self.manager = ManagerBot(1, league_id=league_id)
        # self.league_id = self.manager.lg.league_id
        self.roster_display_order = ['C', 'LW', 'RW', 'D', 'BN', 'G', 'IR']
        self.initUI()
        pass
    
    def initUI(self):
        self.setWindowTitle(self.title)
        self.layout_screen()
        self.show()

    def refresh_pushed(self):
        print("Refresh pressed")
        self.player_drafted(self.draft_ids[self.last_draft_count])
        self.last_draft_count += 1

    def handle_team_roster_changed(self, index):
            item = self.team_combo_box.model().itemFromIndex(index)
            print("Do something with the selected item")

    def layout_screen(self):
        projection_columns = {'Name':'name', 'POS':'position', 'Team':'team', 'CSH':'csh_rank', 'Preseason':'preseason_rank', 'Current':'current_rank', 'GP':'GP','Score':'fantasy_score'} 
        for cat in self.manager.stat_categories:
            projection_columns[cat] = cat

        layout = QHBoxLayout()
        projection_layout = QVBoxLayout()
        projection_table = QTableView()
        projections = retrieve_yahoo_projections(self.manager.lg.league_id, self.manager.stat_categories)
        projections['fantasy_score'] = round(projections['fantasy_score'], 3)
        self.projections_model = PandasModel(projections, column_headers=projection_columns)

        projection_table.setModel(self.projections_model)
        projection_layout.addWidget(projection_table)

        # projections_model.setData(2, QBrush(QtCore.Qt.red), QtCore.Qt.BackgroundRole)

        roster_layout = QVBoxLayout()

        roster_team_selection = QHBoxLayout()
        refresh_button = QPushButton("refresh")
        refresh_button.clicked.connect(self.refresh_pushed)
        roster_team_selection.addWidget(refresh_button)

        roster_team_selection.addWidget(QLabel("Team: "))
        self.team_combo_box = QComboBox()

        self.team_combo_box.view().pressed.connect(self.handle_team_roster_changed)
        for team in self.manager.lg.teams():
            self.team_combo_box.addItem(team['name'])
        # team_combo_box.addItems(['BulgeTheTwine','Keep Your Head Up'])
        roster_team_selection.addWidget(self.team_combo_box)

        roster_layout.addLayout(roster_team_selection)
        roster_table = QTableWidget()
        roster_table.setRowCount(16)
        roster_table.setColumnCount(2)
        roster_layout.addWidget(roster_table)


        layout.addLayout(projection_layout, stretch=2)
        layout.addLayout(roster_layout)
        self.setLayout(layout)

    def player_drafted(self, player_id):
        print(f"Player1 drafted was: {player_id}" )
        self.projections_model.player_drafted(player_id)
        self.projections_model.layoutChanged.emit()
    

# app = QApplication([])

# label = QLabel('League: ')
# label.show()

# app.exec_()
# pass
if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = App()
    runnable = Runnable()
    runnable.set_app(ex)
    runnable.set_manager(ex.manager)
    QThreadPool.globalInstance().start(runnable)
    sys.exit(app.exec_())