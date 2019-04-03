from pandas import DataFrame

from archetypal import EnergySeries


class EnergyProfiles(DataFrame):
    """An EnergyProfiles object is a pandas.DataFrame that has energy related
    data. In addition to the standard DataFrame constructor arguments,
    EnergyProfiles also accepts the following keyword arguments:


    """

    @property
    def _constructor(self):
        return EnergyProfiles

    @property
    def _constructor_sliced(self):
        return EnergySeries
