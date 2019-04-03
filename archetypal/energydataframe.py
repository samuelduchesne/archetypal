from pandas import DataFrame

from archetypal import EnergySeries


class EnergyDataFrame(DataFrame):
    """An EnergyDataFrame object is a pandas.DataFrame that has energy related
    data. In addition to the standard DataFrame constructor arguments,
    EnergyDataFrame also accepts the following keyword arguments:


    """

    @property
    def _constructor(self):
        return EnergyDataFrame

    @property
    def _constructor_sliced(self):
        return EnergySeries
