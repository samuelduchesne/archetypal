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

    def __init__(self, *args, **kwargs):
        super(EnergyDataFrame, self).__init__(*args, **kwargs)

    def __getitem__(self, key):
        """
        return a EnergySeries.
        """
        result = super(EnergyDataFrame, self).__getitem__(key)
        if isinstance(result, Series):
            result.__class__ = EnergySeries
        elif isinstance(result, DataFrame):
            result.__class__ = EnergyDataFrame
        return result