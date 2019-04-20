import logging as lg
import os
import time
import warnings

import numpy as np
import pandas as pd
import pint
from matplotlib import pyplot as plt, cm
from matplotlib.colors import LightSource
from pandas import Series, DataFrame, concat, MultiIndex, date_range
from sklearn import preprocessing

import archetypal
from archetypal import log, rmse, piecewise, settings


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

    def __new__(cls, data, frequency=None, from_units=None,
                 profile_type='undefinded',
                 index=None, dtype=None, copy=True, name=None,
                 fastpath=False, base_year=2017, normalize=False,
                 is_sorted=False, ascending=False, archetypes=None,
                 concurrent_sort=False, to_units='kW'):
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
        """Retruns a discretized pandas.Series

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
                # Todo hours need to work fow datetime index
                hours.extend([len(sub)])
                hours_bounds = [(0, len(sub)) for i in range(0, n_bins + 1)]

                start_time = time.time()
                log('discretizing EnergySeries {}'.format(name), lg.DEBUG)
                res = minimize(rmse, np.array(hours + sf), args=(sub.values),
                               method='L-BFGS-B',
                               bounds=hours_bounds + sf_bounds,
                               options=dict(disp=True))
                log('Completed discretization in {:,.2f} seconds'.format(
                    time.time() - start_time), lg.DEBUG)
                edges[name] = res.x[0:n_bins + 1]
                ampls[name] = res.x[n_bins + 1:]
                results[name] = Series(piecewise(res.x))
            self.bin_edges_ = Series(edges).apply(Series)
            self.bin_scaling_factors_ = DataFrame(ampls)

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

        Wraps the ``plot_energyseries()`` function, and documentation is copied
        from there.
        """
        return plot_energyseries(self, *args, **kwargs)

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


def save_and_show(fig, ax, save, show, close, filename, file_format, dpi,
                  axis_off, extent):
    """Save a figure to disk and show it, as specified.

    Args:
        extent:
        fig (matplotlib.figure.Figure): the figure
        ax (matplotlib.axes.Axes): the axes
        save (bool): whether to save the figure to disk or not
        show (bool): whether to display the figure or not
        close (bool): close the figure (only if show equals False) to prevent
            display
        filename (string): the name of the file to save
        file_format (string): the format of the file to save (e.g., 'jpg',
            'png', 'svg')
        dpi (int): the resolution of the image file if saving (Dots per inch)
        axis_off (bool): if True matplotlib axis was turned off by plot_graph so
            constrain the saved figure's extent to the interior of the axis

    Returns:
        (tuple) fig, ax
    """
    # save the figure if specified

    if save:
        start_time = time.time()

        # create the save folder if it doesn't already exist
        if not os.path.exists(settings.imgs_folder):
            os.makedirs(settings.imgs_folder)
        path_filename = os.path.join(settings.imgs_folder,
                                     os.extsep.join([filename, file_format]))

        if not isinstance(ax, (np.ndarray, list)):
            ax = [ax]
        if file_format == 'svg':
            for ax in ax:
                # if the file_format is svg, prep the fig/ax a bit for saving
                ax.axis('off')
                ax.set_position([0, 0, 1, 1])
                ax.patch.set_alpha(0.)
            fig.patch.set_alpha(0.)
            fig.savefig(path_filename, bbox_inches=0, format=file_format,
                        facecolor=fig.get_facecolor(), transparent=True)
        else:
            if extent is None:
                if len(ax) == 1:
                    if axis_off:
                        for ax in ax:
                            # if axis is turned off, constrain the saved
                            # figure's extent to the interior of the axis
                            extent = ax.get_window_extent().transformed(
                                fig.dpi_scale_trans.inverted())
                else:
                    extent = 'tight'
            fig.savefig(path_filename, dpi=dpi, bbox_inches=extent,
                        format=file_format, facecolor=fig.get_facecolor(),
                        transparent=True)
        log('Saved the figure to disk in {:,.2f} seconds'.format(time.time() -
                                                                 start_time))

    # show the figure if specified
    if show:
        start_time = time.time()
        plt.show()
        # fig.show()
        log('Showed the plot in {:,.2f} seconds'.format(time.time() -
                                                        start_time))
    # if show=False, close the figure if close=True to prevent display
    elif close:
        plt.close()

    return fig, ax


def plot_energyseries(energy_series, kind='polygon', axis_off=True, cmap=None,
                      fig_height=None, fig_width=6, show=True, view_angle=-60,
                      save=False, close=False, dpi=300, file_format='png',
                      color=None, axes=None, vmin=None, vmax=None,
                      filename=None, **kwargs):
    """

    Args:
        energy_series (EnergySeries):
        kind (str):
        axis_off (bool):
        cmap ():
        fig_height (float):
        fig_width (float):
        show (bool):
        view_angle (float):
        save (bool):
        close (bool):
        dpi (int):
        file_format (str):
        color (str):
        axes ():
        vmin (float):
        vmax (float):
        filename (str):
        **kwargs:

    Returns:

    """
    if energy_series.empty:
        warnings.warn("The EnergyProgile you are attempting to plot is "
                      "empty. Nothing has been displayed.", UserWarning)
        return axes

    import matplotlib.pyplot as plt
    # noinspection PyUnresolvedReferences
    from mpl_toolkits.mplot3d import Axes3D

    if isinstance(energy_series.index, pd.MultiIndex):
        groups = energy_series.groupby(level=0)
        nax = len(groups)
    else:
        nax = 1
        groups = [('unnamed', energy_series)]

    if fig_height is None:
        fig_height = fig_width * nax

    # Set up plot
    fig, axes = plt.subplots(nax, 1, subplot_kw=dict(projection='3d'),
                             figsize=(fig_width, fig_height), dpi=dpi)
    if not isinstance(axes, np.ndarray):
        axes = [axes]

    for ax, (name, profile) in zip(axes, groups):
        values = profile.values

        vmin = values.min() if vmin is None else vmin
        vmax = values.max() if vmax is None else vmax

        if kind == 'polygon':
            z = values.reshape(365, 24)
            nrows, ncols = z.shape
            xs = np.linspace(0, 23, ncols)
            # y = np.linspace(0, 364, nrows)
            # The ith polygon will appear on the plane y = zs[i]
            zs = np.linspace(0, 364, nrows)
            verts = []
            for i in zs:
                ys = z[int(i), :]
                verts.append(_polygon_under_graph(xs, ys))

            _plot_poly_collection(ax, verts, zs,
                                  edgecolors=kwargs.get('edgecolors', None),
                                  facecolors=kwargs.get('facecolors', None),
                                  linewidths=kwargs.get('linewidths', None),
                                  cmap=cmap)
        elif kind == 'surface':
            z = values.reshape(365, 24)
            nrows, ncols = z.shape
            x = np.linspace(1, 24, ncols)
            y = np.linspace(1, 365, nrows)
            x, y = np.meshgrid(x, y)
            _plot_surface(ax, x, y, z, cmap=cmap, **kwargs)
        else:
            raise NameError('plot kind "{}" is not supported'.format(kind))

        if filename is None:
            filename = 'unnamed'

        # set the extent of the figure
        ax.set_xlim3d(-1, 24)
        ax.set_xlabel('X')
        ax.set_ylim3d(-1, 365)
        ax.set_ylabel('Y')
        ax.set_zlim3d(vmin, vmax)
        ax.set_zlabel('Z')

        # configure axis appearance
        xaxis = ax.xaxis
        yaxis = ax.yaxis
        zaxis = ax.zaxis

        xaxis.get_major_formatter().set_useOffset(False)
        yaxis.get_major_formatter().set_useOffset(False)
        zaxis.get_major_formatter().set_useOffset(False)

        # if axis_off, turn off the axis display set the margins to zero and
        # point the ticks in so there's no space around the plot
        if axis_off:
            ax.axis('off')
            ax.margins(0)
            ax.tick_params(which='both', direction='in')
            xaxis.set_visible(False)
            yaxis.set_visible(False)
            zaxis.set_visible(False)
            fig.canvas.draw()
        if view_angle is not None:
            ax.view_init(30, view_angle)
            ax.set_proj_type(kwargs.get('proj_type', 'persp'))
            fig.canvas.draw()
    fig, axes = save_and_show(fig=fig, ax=axes, save=save, show=show,
                              close=close, filename=filename,
                              file_format=file_format, dpi=dpi,
                              axis_off=axis_off, extent=None)
    return fig, axes


def _plot_poly_collection(ax, verts, zs=None, color=None, cmap=None,
                          vmin=None, vmax=None, **kwargs):
    from matplotlib.collections import PolyCollection

    # if None in zs:
    #     zs = None

    # color=None overwrites specified facecolor/edgecolor with default color
    if color is not None:
        kwargs['color'] = color
    import matplotlib as mpl
    norm = mpl.colors.Normalize(vmin=vmin, vmax=vmax)

    poly = PolyCollection(verts, **kwargs)
    if zs is not None:
        poly.set_array(np.asarray(zs))
        poly.set_cmap(cmap)
        poly.set_clim(vmin, vmax)

    ax.add_collection3d(poly, zs=zs, zdir='y')
    # ax.autoscale_view()
    return poly


def _plot_surface(ax, x, y, z, cmap=None, **kwargs):
    if cmap is None:
        cmap = cm.gist_earth

    ls = LightSource(270, 45)
    # To use a custom hillshading mode, override the built-in shading and pass
    # in the rgb colors of the shaded surface calculated from "shade".
    rgb = ls.shade(z, cmap=cm.get_cmap(cmap), vert_exag=0.1, blend_mode='soft')
    surf = ax.plot_surface(x, y, z, rstride=1, cstride=1, facecolors=rgb,
                           linewidth=0, antialiased=False, shade=False,
                           **kwargs)
    return surf


def _polygon_under_graph(xlist, ylist):
    """Construct the vertex list which defines the polygon filling the space
    under
    the (xlist, ylist) line graph.  Assumes the xs are in ascending order."""
    return [(xlist[0], 0.), *zip(xlist, ylist), (xlist[-1], 0.)]


EnergySeries.plot3d.__doc__ = plot_energyseries.__doc__
