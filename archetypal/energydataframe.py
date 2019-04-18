from pandas import DataFrame

from archetypal import EnergySeries


class EnergyDataFrame(DataFrame):
    """An EnergyDataFrame object is a pandas.DataFrame that has energy related
    data. In addition to the standard DataFrame constructor arguments,
    EnergyDataFrame also accepts the following keyword arguments:


    """
    _metadata = ['from_units']

    def __init__(self, *args, **kwargs):
        from_units = kwargs.pop('from_units', None)
        super(EnergyDataFrame, self).__init__(*args, **kwargs)
        self.from_units = from_units
        if from_units is not None:
            self.set_unit(from_units, inplace=True)

    def set_unit(self, from_unit, inplace):
        import pint
        ureg = pint.UnitRegistry()

        if inplace:
            frame = self
        else:
            frame = self.copy()

        self.from_units = ureg.parse_expression(from_unit)

        if not inplace:
            return frame

    @property
    def _constructor(self):
        return EnergyDataFrame

    @property
    def _constructor_sliced(self):
        return EnergySeries
