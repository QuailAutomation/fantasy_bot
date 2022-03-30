class PlayerSelector:
    def __init__(self, df, team_id, opp_id) -> None:
        self._df= df
        self.my_team_id = team_id
        self.my_opp_id = opp_id

    @property    
    def fa(self):
        return self._df.fantasy_status == 'FA'

    @property    
    def out(self):
        return self._df.status != 'O'

    def perc_own(self, percent, greater=True):
        # TODO add inclusivity param?
        if greater:
            return self._df.percent_owned > percent
        else:
            return self._df.percent_owned < percent
    
    @property
    def my_team(self):
        return self._df.fantasy_status == self.my_team_id
    
    @property
    def opponent(self):
        return self._df.fantasy_status == self.my_opp_id

    @property
    def ir(self):
        return (self._df.status == 'IR') | (self._df.status == 'IR-LT')
# & ((all_projections.status != 'IR') & (all_projections.status != 'IR-LT'))