import logging as lg
import time

import numpy as np
import pint
from pandas import Series, DataFrame, concat, MultiIndex
from sklearn import preprocessing
from archetypal import log, rmse, piecewise, plot_energyprofile


class EnergySeries(Series):
    """A Series object designed to store energy related data.
    """

    @property
    def _constructor(self):
        return EnergySeries

    _metadata = ['bin_edges_', 'bin_scaling_factors_', 'profile_type',
                 'base_year', 'frequency', 'from_units',
                 'is_sorted', 'to_units', 'archetypes', 'converted_',
                 'concurrent_sort_']

    def __finalize__(self, other, method=None, **kwargs):
        """ propagate metadata from other to self """
        # NOTE: backported from pandas master (upcoming v0.13)
        for name in self._metadata:
            object.__setattr__(self, name, getattr(other, name, None))
        return self

    def __new__(cls, *args, **kwargs):
        kwargs.pop('frequency', None)
        kwargs.pop('from_units', None)
        arr = Series.__new__(cls)
        if type(arr) is EnergySeries:
            return arr
        else:
            return arr.view(EnergySeries)

    def __init__(self, data, frequency=None, from_units=None,
                 profile_type='undefinded',
                 index=None, dtype=None, copy=True, name=None,
                 fastpath=False, base_year=2017, normalize=False,
                 is_sorted=False, ascending=False, archetypes=None,
                 concurrent_sort=False, to_units='kW'):
        super(EnergySeries, self).__init__(data=data, index=index,
                                           dtype=dtype, name=name,
                                           copy=copy, fastpath=fastpath)
        self.bin_edges_ = None
        self.bin_scaling_factors_ = None
        self.profile_type = profile_type
        self.frequency = frequency
        self.base_year = base_year
        self.from_units = pint.UnitRegistry().parse_expression(from_units)
        self.archetypes = archetypes
        self.to_units = pint.UnitRegistry().parse_expression(to_units)
        self.converted_ = False
        self.concurrent_sort_ = concurrent_sort
        # handle sorting of the data
        if is_sorted:
            self.is_sorted = True
            if concurrent_sort:
                self.concurrent_sort(ascending=ascending, inplace=True)
            else:
                self.sort_values(ascending=ascending, inplace=True)
                self.reset_index(drop=True, inplace=True)
        else:
            self.is_sorted = False

        # handle archetype names
        if isinstance(self.index, MultiIndex):
            self.archetypes = list(set(self.index.get_level_values(level=0)))
        else:
            self.archetypes = None

        # handle normalization
        if normalize:
            self.normalize(inplace=True)

    def unit_conversion(self, to_units=None, inplace=False):
        """returns the multiplier to convert from_units"""
        from pint import UnitRegistry
        a = UnitRegistry()
        if to_units is None:
            to_units = self.to_units
        else:
            to_units = a.parse_expression(to_units)
        to_multiple = self.from_units.to(
            to_units.units).m
        result = self.apply(lambda x: x * to_multiple)
        result.__class__ = EnergySeries
        result.converted_ = True
        result.from_units = to_units
        if inplace:
            self.update(result)
            self.__finalize__(result)
        else:
            return result

    def concurrent_sort(self, ascending=False, inplace=False, level=0):
        if isinstance(self.index, MultiIndex):
            concurrent = self.unstack(level=level)
            concurrent_sum = concurrent.sum(axis=1)

            sortedIdx = concurrent_sum.sort_values(ascending=ascending).index

            result = concurrent.loc[sortedIdx, :]
            result.index = concurrent.index
            result = result.stack().swaplevel()

            if inplace:
                self.update(result)
                self.__finalize__(result)
            else:
                return result  # todo: make sure results has all the metadata

    def normalize(self, feature_range=(0, 1), inplace=False):
        """Returns a normalized EnergySeries"""
        scaler = preprocessing.MinMaxScaler(feature_range=feature_range)
        if self.archetypes:
            result = concat({name: Series(
                scaler.fit_transform(sub.values.reshape(-1, 1)).ravel()) for
                name, sub in self.groupby(level=0)}).sort_index()
            result = self._constructor(result)
        else:
            result = Series(scaler.fit_transform(self.values.reshape(-1,
                                                                        1)).ravel())
            result = self._constructor(result)
            result.from_units = pint.UnitRegistry().dimensionless
        if inplace:
            self._update_inplace(result)
        else:
            return result  # todo: make sure result has all the metadata

    def ldc_source(self, SCOPH=4, SCOPC=4):
        """Returns the Load Duration Curve from the source side of
        theoretical Heat Pumps

        Args:
            SCOPH: Seasonal COP in Heating
            SCOPC: Seasonal COP in Cooling

        Returns:
            (EnergySeries) Load Duration Curve
        """

        result = self.ldc.apply(lambda x: x * (1 - 1 / SCOPH) if x > 0
        else x * (1 + 1 / SCOPC))
        return result

    def source_side(self, SCOPH=None, SCOPC=None):
        """Returns the Source Side EnergySeries given a Seasonal COP.
        Negative values are considered like Cooling Demand.

        Args:
            SCOPH: Seasonal COP in Heating
            SCOPC: Seasonal COP in Cooling

        Returns:
            (EnergySeries) Load Duration Curve
        """
        if SCOPC or SCOPH:
            result = self.apply(
                lambda x: x * (1 - 1 / SCOPH) if SCOPH else x * (1 +
                                                                 1 / SCOPC))
            return result
        else:
            raise ValueError('Please provide a SCOPH or a SCOPC')

    def discretize(self, n_bins=3, inplace=False):
        """Retruns a discretized pd.Series

        Args:
            n_bins (int): Number of bins or steps to discretize the function
            inplace (bool): if True, perform operation in-place

        Returns:

        """
        try:
            from scipy.optimize import minimize
            from itertools import chain
        except ImportError:
            raise ImportError('The sklearn package must be installed to '
                              'use this optional feature.')
        if self.archetypes:
            # if multiindex, group and apply operation on each group.
            # combine at the end
            results = {}
            edges = {}
            ampls = {}
            for name, sub in self.groupby(level=0):
                hour_of_min = sub.time_at_min[1]

                sf = [1 / (i * 1.01) for i in range(1, n_bins + 1)]
                sf.extend([sub.min()])
                sf_bounds = [(0, sub.max()) for i in range(0, n_bins + 1)]
                hours = [hour_of_min - hour_of_min * 1 / (i * 1.01) for i in
                         range(1, n_bins + 1)]
                # Todo hours need to work fow datatime index
                hours.extend([8760])
                hours_bounds = [(0, 8760) for i in range(0, n_bins + 1)]

                start_time = time.time()
                log('discretizing EnergySeries {}'.format(name), lg.DEBUG)
                res = minimize(rmse, np.array(hours + sf), args=(self.values),
                               method='L-BFGS-B',
                               bounds=hours_bounds + sf_bounds,
                               options=dict(disp=True))
                log('Completed discretization in {:,.2f} seconds'.format(
                    time.time() - start_time), lg.DEBUG)
                edges[name] = res.x[0:n_bins + 1]
                ampls[name] = res.x[n_bins + 1:]
                results[name] = Series(piecewise(res.x))
            self.bin_edges_ = Series(edges).apply(Series)
            self.bin_scaling_factors_ = DataFrame(ampls,
                                                     index=np.round(
                                                         edges).astype(int),
                                                     columns=['scaling_factor'])

            result = concat(results)
        else:
            hour_of_min = self.time_at_min

            sf = [1 / (i * 1.01) for i in range(1, n_bins + 1)]
            sf.extend([self.min()])
            sf_bounds = [(0, self.max()) for i in range(0, n_bins + 1)]
            hours = [hour_of_min - hour_of_min * 1 / (i * 1.01) for i in
                     range(1, n_bins + 1)]
            hours.extend([len(self)])
            hours_bounds = [(0, len(self)) for i in range(0, n_bins + 1)]

            start_time = time.time()
            # log('discretizing EnergySeries {}'.format(name), lg.DEBUG)
            res = minimize(rmse, np.array(hours + sf), args=(self.values),
                           method='L-BFGS-B',
                           bounds=hours_bounds + sf_bounds,
                           options=dict(disp=True))
            log('Completed discretization in {:,.2f} seconds'.format(
                time.time() - start_time), lg.DEBUG)
            edges = res.x[0:n_bins + 1]
            ampls = res.x[n_bins + 1:]
            result = Series(piecewise(res.x))
            bin_edges = Series(edges).apply(Series)
            self.bin_edges_ = bin_edges
            bin_edges.loc[-1, 0] = 0
            bin_edges.sort_index(inplace=True)
            bin_edges = bin_edges.diff().dropna()
            bin_edges = bin_edges.round()
            self.bin_scaling_factors_ = DataFrame({'duration': bin_edges[
                0], 'scaling factor': ampls})
            self.bin_scaling_factors_.index = np.round(edges).astype(int)

        if inplace:
            self.update(result)
            self.__class__ = EnergySeries
            self.__finalize__(result)
        else:
            result.__class__ = EnergySeries
            return result.__finalize__(self)

    def plot3d(self, *args, **kwargs):
        """Generate a plot of the EnergySeries.

        If the ``column`` parameter is given, colors plot according to values
        in that column, otherwise calls ``GeoSeries.plot()`` on the
        ``geometry`` column.

        Wraps the ``plot_energyprofile()`` function, and documentation is copied
        from there.
        """
        return plot_energyprofile(self, *args, **kwargs)

    plot3d.__doc__ = plot_energyprofile.__doc__

    @property
    def units(self):
        return self.from_units.units

    @property
    def p_max(self):
        if isinstance(self.index, MultiIndex):
            return self.groupby(level=0).max()
        else:
            return self.max()

    @property
    def monthly(self):
        if isinstance(self.index, MultiIndex):
            return self.groupby(level=0).max()
        else:
            datetimeindex = date_range(freq=self.frequency,
                                          start='{}-01-01'.format(
                                              self.base_year),
                                          periods=self.size)
            self_copy = self.copy()
            self_copy.index = datetimeindex
            self_copy = self_copy.resample('M').mean()
            self_copy.frequency = 'M'
            return EnergySeries(self_copy, frequency='M',
                                from_units=self.from_units)

    @property
    def capacity_factor(self):
        max = self.max()
        mean = self.mean()
        return mean / max

    @property
    def bin_edges(self):
        """"""
        return self.bin_edges_

    @property
    def time_at_min(self):
        return self.idxmin()

    @property
    def bin_scaling_factors(self):
        return self.bin_scaling_factors_

    @property
    def duration_scaling_factor(self):
        return list(map(tuple, self.bin_scaling_factors.values))

    @property
    def ldc(self):
        nb_points = len(self)
        newdata = self.sort_values(ascending=False)
        newdata.index = range(0, nb_points)
        return newdata.__finalize__(self)
