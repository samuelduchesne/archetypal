import copy
import logging as lg
import os
import time
import warnings
from datetime import timedelta

import numpy as np
import pandas as pd
import tsam.timeseriesaggregation as tsam
from matplotlib import pyplot as plt, cm
from matplotlib.colors import LightSource
from pandas import Series, DataFrame, concat, MultiIndex, date_range
from sklearn import preprocessing

import archetypal
from archetypal import log, rmse, piecewise, settings


class EnergySeries(Series):
    """A Series object designed to store energy related data."""

    @property
    def _constructor(self):
        return EnergySeries

    _metadata = [
        "name",
        "bin_edges_",
        "bin_scaling_factors_",
        "profile_type",
        "base_year",
        "frequency",
        "units",
        "sort_values",
        "to_units",
        "converted_",
        "concurrent_sort_",
    ]

    def __new__(
        cls,
        data,
        frequency=None,
        units=None,
        profile_type="undefinded",
        index=None,
        dtype=None,
        copy=True,
        name=None,
        fastpath=False,
        base_year=2018,
        normalize=False,
        sort_values=False,
        ascending=False,
        archetypes=None,
        concurrent_sort=False,
        to_units=None,
        use_timeindex=False,
    ):
        """
        Args:
            data:
            frequency:
            units:
            profile_type:
            index:
            dtype:
            copy:
            name:
            fastpath:
            base_year:
            normalize:
            sort_values:
            ascending:
            archetypes:
            concurrent_sort:
            to_units:
            use_timeindex:
        """
        self = super(EnergySeries, cls).__new__(cls)
        return self

    def __init__(
        self,
        data,
        frequency=None,
        units=None,
        profile_type="undefinded",
        index=None,
        dtype=None,
        copy=True,
        name=None,
        fastpath=False,
        base_year=2018,
        normalize=False,
        sort_values=False,
        ascending=False,
        archetypes=None,
        concurrent_sort=False,
        to_units=None,
        use_timeindex=False,
    ):
        """
        Args:
            data:
            frequency:
            units:
            profile_type:
            index:
            dtype:
            copy:
            name:
            fastpath:
            base_year:
            normalize:
            sort_values:
            ascending:
            archetypes:
            concurrent_sort:
            to_units:
            use_timeindex:
        """
        super(EnergySeries, self).__init__(
            data=data, index=index, dtype=dtype, name=name, copy=copy, fastpath=fastpath
        )
        self.bin_edges_ = None
        self.bin_scaling_factors_ = None
        self.profile_type = profile_type
        self.frequency = frequency
        self.base_year = base_year
        self.units = settings.unit_registry.parse_expression(units).units
        self.archetypes = archetypes
        self.to_units = settings.unit_registry.parse_expression(to_units).units
        self.converted_ = False
        self.concurrent_sort_ = concurrent_sort
        # handle sorting of the data
        if sort_values:
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

        # handle unit conversion
        if to_units and units:
            self.unit_conversion(to_units=to_units, inplace=True)

        # handle DateTimeIndex
        if index is None and use_timeindex:
            start_date = str(self.base_year) + "0101"
            if isinstance(self.index, MultiIndex):
                newindex = self.index  # todo: finish this
            else:
                newindex = pd.date_range(
                    start=start_date, freq=self.frequency, periods=len(self)
                )
            self.index = newindex

    @classmethod
    def from_sqlite(
        cls,
        df,
        name=None,
        base_year=2018,
        units=None,
        normalize=False,
        sort_values=False,
        ascending=False,
        concurrent_sort=False,
        to_units=None,
        agg_func="sum",
    ):
        """Create a.

        Args:
            df (DataFrame):
            name:
            base_year:
            units:
            normalize:
            sort_values:
            ascending:
            concurrent_sort:
            to_units:
            agg_func (callable): The aggregation function to use in the case
                that multiple values have the same index value. If a function,
                must either work when passed a DataFrame or when passed to
                DataFrame.apply. For a DataFrame, can pass a dict, if the keys
                are DataFrame column names.

                Accepted Combinations are:
                    - string function name
                    - function
                    - list of functions
                    - dict of column names -> functions (or list of functions)
        """
        index = pd.to_datetime(
            {
                "year": base_year,
                "month": df.Month,
                "day": df.Day,
                "hour": df.Hour,
                "minute": df.Minute,
            }
        )
        # Adjust timeindex by timedelta
        index -= df.Interval.apply(lambda x: timedelta(minutes=x))
        index = pd.DatetimeIndex(index)
        # get data
        data = df.Value
        data.index = index
        units = [units] if units else set(df.Units)
        if len(units) > 1:
            raise ValueError("The DataFrame contains mixed units: {}".format(units))
        else:
            units = next(iter(units), None)
        # group data by index value (level=0) using the agg_func
        if agg_func:
            grouped_Data = data.groupby(level=0).agg(agg_func)
        else:
            df["DateTimeIndex"] = index
            grouped_Data = df.set_index(["DateTimeIndex", "Name"]).Value
        # Since we create the index, use_timeindex must be false
        return cls(
            grouped_Data.values,
            name=name,
            units=units,
            index=grouped_Data.index,
            use_timeindex=False,
            base_year=base_year,
            normalize=normalize,
            sort_values=sort_values,
            ascending=ascending,
            concurrent_sort=concurrent_sort,
            to_units=to_units,
        )

    def unit_conversion(self, to_units=None, inplace=False):
        """returns the multiplier to convert units

        Args:
            to_units (pint.Unit):
            inplace:
        """
        reg = settings.unit_registry
        if to_units is None:
            to_units = self.to_units
        else:
            to_units = reg.parse_expression(to_units).units
        cdata = reg.Quantity(self.values, self.units).to(to_units).m
        result = self.apply(lambda x: x)
        result.update(pd.Series(cdata, index=result.index))
        result.__class__ = EnergySeries
        result.converted_ = True
        result.units = to_units
        if inplace:
            self._update_inplace(result)
            self.__finalize__(result)
        else:
            return result

    def concurrent_sort(self, ascending=False, inplace=False, level=0):
        """
        Args:
            ascending:
            inplace:
            level:
        """
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
        """Returns a normalized EnergySeries

        Args:
            feature_range:
            inplace:
        """
        scaler = preprocessing.MinMaxScaler(feature_range=feature_range)
        if self.archetypes:
            result = concat(
                {
                    name: Series(
                        scaler.fit_transform(sub.values.reshape(-1, 1)).ravel()
                    )
                    for name, sub in self.groupby(level=0)
                }
            ).sort_index()
            result = self._constructor(result)
        else:
            result = Series(scaler.fit_transform(self.values.reshape(-1, 1)).ravel())
            result = self._constructor(result)
            result.units = settings.unit_registry.dimensionless
        if inplace:
            self._update_inplace(result)
        else:
            return result  # todo: make sure result has all the metadata

    def ldc_source(self, SCOPH=4, SCOPC=4):
        """Returns the Load Duration Curve from the source side of theoretical
        Heat Pumps

        Args:
            SCOPH: Seasonal COP in Heating
            SCOPC: Seasonal COP in Cooling

        Returns:
            (EnergySeries) Load Duration Curve
        """

        result = self.ldc.apply(
            lambda x: x * (1 - 1 / SCOPH) if x > 0 else x * (1 + 1 / SCOPC)
        )
        return result

    def source_side(self, SCOPH=None, SCOPC=None):
        """Returns the Source Side EnergySeries given a Seasonal COP. Negative
        values are considered like Cooling Demand.

        Args:
            SCOPH: Seasonal COP in Heating
            SCOPC: Seasonal COP in Cooling

        Returns:
            (EnergySeries) Load Duration Curve
        """
        if SCOPC or SCOPH:
            result = self.apply(
                lambda x: x * (1 - 1 / SCOPH) if SCOPH else x * (1 + 1 / SCOPC)
            )
            return result
        else:
            raise ValueError("Please provide a SCOPH or a SCOPC")

    def discretize_tsam(
        self,
        resolution=None,
        noTypicalPeriods=10,
        hoursPerPeriod=24,
        clusterMethod="hierarchical",
        evalSumPeriods=False,
        sortValues=False,
        sameMean=False,
        rescaleClusterPeriods=True,
        weightDict=None,
        extremePeriodMethod="None",
        solver="glpk",
        roundOutput=None,
        addPeakMin=None,
        addPeakMax=None,
        addMeanMin=None,
        addMeanMax=None,
    ):
        """uses tsam

        Args:
            resolution:
            noTypicalPeriods:
            hoursPerPeriod:
            clusterMethod:
            evalSumPeriods:
            sortValues:
            sameMean:
            rescaleClusterPeriods:
            weightDict:
            extremePeriodMethod:
            solver:
            roundOutput:
            addPeakMin:
            addPeakMax:
            addMeanMin:
            addMeanMax:
        """
        try:
            import tsam.timeseriesaggregation as tsam
        except ImportError:
            raise ImportError("tsam is required for discretize_tsam()")
        if not isinstance(self.index, pd.DatetimeIndex):
            raise TypeError("To use tsam, index of series must be a " "DateTimeIndex")
        if isinstance(self, Series):
            timeSeries = pd.DataFrame(self)
        else:
            timeSeries = self.copy()
        agg = tsam.TimeSeriesAggregation(
            timeSeries,
            resolution=resolution,
            noTypicalPeriods=noTypicalPeriods,
            hoursPerPeriod=hoursPerPeriod,
            clusterMethod=clusterMethod,
            evalSumPeriods=evalSumPeriods,
            sortValues=sortValues,
            sameMean=sameMean,
            rescaleClusterPeriods=rescaleClusterPeriods,
            weightDict=weightDict,
            extremePeriodMethod=extremePeriodMethod,
            solver=solver,
            roundOutput=roundOutput,
            addPeakMin=addPeakMin,
            addPeakMax=addPeakMax,
            addMeanMin=addMeanMin,
            addMeanMax=addMeanMax,
        )

        agg.createTypicalPeriods()
        results = agg.predictOriginalData()
        results = EnergySeries(results.iloc[:, 0])
        # results._internal_names += agg.clusterOrder
        return results.__finalize__(self)

    def discretize(self, n_bins=3, inplace=False):
        """Retruns a discretized pandas.Series

        Args:
            n_bins (int): Number of bins or steps to discretize the function
            inplace (bool): if True, perform operation in-place
        """
        try:
            from scipy.optimize import minimize
            from itertools import chain
        except ImportError:
            raise ImportError(
                "The sklearn package must be installed to " "use this optional feature."
            )
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
                hours = [
                    hour_of_min - hour_of_min * 1 / (i * 1.01)
                    for i in range(1, n_bins + 1)
                ]
                # Todo hours need to work fow datetime index
                hours.extend([len(sub)])
                hours_bounds = [(0, len(sub)) for i in range(0, n_bins + 1)]

                start_time = time.time()
                log("discretizing EnergySeries {}".format(name), lg.DEBUG)
                res = minimize(
                    rmse,
                    np.array(hours + sf),
                    args=(sub.values),
                    method="L-BFGS-B",
                    bounds=hours_bounds + sf_bounds,
                    options=dict(disp=True),
                )
                log(
                    "Completed discretization in {:,.2f} seconds".format(
                        time.time() - start_time
                    ),
                    lg.DEBUG,
                )
                edges[name] = res.x[0 : n_bins + 1]
                ampls[name] = res.x[n_bins + 1 :]
                results[name] = Series(piecewise(res.x))
            self.bin_edges_ = Series(edges).apply(Series)
            self.bin_scaling_factors_ = DataFrame(ampls)

            result = concat(results)
        else:
            hour_of_min = self.time_at_min

            sf = [1 / (i * 1.01) for i in range(1, n_bins + 1)]
            sf.extend([self.min()])
            sf_bounds = [(0, self.max()) for i in range(0, n_bins + 1)]
            hours = [
                hour_of_min - hour_of_min * 1 / (i * 1.01) for i in range(1, n_bins + 1)
            ]
            hours.extend([len(self)])
            hours_bounds = [(0, len(self)) for i in range(0, n_bins + 1)]

            start_time = time.time()
            # log('discretizing EnergySeries {}'.format(name), lg.DEBUG)
            res = minimize(
                rmse,
                np.array(hours + sf),
                args=(self.values),
                method="L-BFGS-B",
                bounds=hours_bounds + sf_bounds,
                options=dict(disp=True),
            )
            log(
                "Completed discretization in {:,.2f} seconds".format(
                    time.time() - start_time
                ),
                lg.DEBUG,
            )
            edges = res.x[0 : n_bins + 1]
            ampls = res.x[n_bins + 1 :]
            result = Series(piecewise(res.x))
            bin_edges = Series(edges).apply(Series)
            self.bin_edges_ = bin_edges
            bin_edges.loc[-1, 0] = 0
            bin_edges.sort_index(inplace=True)
            bin_edges = bin_edges.diff().dropna()
            bin_edges = bin_edges.round()
            self.bin_scaling_factors_ = DataFrame(
                {"duration": bin_edges[0], "scaling factor": ampls}
            )
            self.bin_scaling_factors_.index = np.round(edges).astype(int)

        if inplace:
            self.update(result)
            self.__class__ = EnergySeries
            self.__finalize__(result)
        else:
            result.__class__ = EnergySeries
            return result.__finalize__(self)

    def unstack(self, level=-1, fill_value=None):
        """
        Args:
            level:
            fill_value:
        """
        from pandas.core.reshape.reshape import unstack

        result = unstack(self, level, fill_value)
        result.__class__ = archetypal.EnergyDataFrame
        return result.__finalize__(self)

    def stack(self, level=-1, dropna=True):
        """
        Args:
            level:
            dropna:
        """
        from pandas.core.reshape.reshape import stack, stack_multiple

        if isinstance(level, (tuple, list)):
            result = stack_multiple(self, level, dropna=dropna)
            return self.__finalize__(result)
        else:
            result = stack(self, level, dropna=dropna)
            return self.__finalize__(result)

    def plot3d(self, *args, **kwargs):
        """Generate a plot of the EnergySeries.

        Wraps the ``plot_energyseries()`` function, and documentation is
        copied from there.

        Args:
            *args:
            **kwargs:
        """
        return plot_energyseries(self, *args, **kwargs)

    def plot2d(self, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        return plot_energyseries_map(self, **kwargs)

    # @property
    # def units(self):
    #     return self.units.units

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
            datetimeindex = date_range(
                freq=self.frequency,
                start="{}-01-01".format(self.base_year),
                periods=self.size,
            )
            self_copy = self.copy()
            self_copy.index = datetimeindex
            self_copy = self_copy.resample("M").mean()
            self_copy.frequency = "M"
            return EnergySeries(self_copy, frequency="M", units=self.units)

    @property
    def capacity_factor(self):
        max = self.max()
        mean = self.mean()
        return mean / max

    @property
    def bin_edges(self):
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
        newdata = self.sort_values(ascending=False).reset_index(drop=True)
        return newdata.__finalize__(self)

    @property
    def nseries(self):
        if self.data.ndim == 1:
            return 1
        else:
            return self.data.shape[1]


def save_and_show(
    fig, ax, save, show, close, filename, file_format, dpi, axis_off, extent
):
    """Save a figure to disk and show it, as specified.

    Args:
        fig (matplotlib.figure.Figure): the figure
        ax (matplotlib.axes.Axes or list(matplotlib.axes.Axes)): the axes
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
        extent:

    Returns:
        (tuple) fig, ax
    """
    # save the figure if specified

    if save:
        start_time = time.time()

        # create the save folder if it doesn't already exist
        if not os.path.exists(settings.imgs_folder):
            os.makedirs(settings.imgs_folder)
        path_filename = os.path.join(
            settings.imgs_folder, os.extsep.join([filename, file_format])
        )

        if not isinstance(ax, (np.ndarray, list)):
            ax = [ax]
        if file_format == "svg":
            for ax in ax:
                # if the file_format is svg, prep the fig/ax a bit for saving
                ax.axis("off")
                ax.set_position([0, 0, 1, 1])
                ax.patch.set_alpha(0.0)
            fig.patch.set_alpha(0.0)
            fig.savefig(
                path_filename,
                bbox_inches=0,
                format=file_format,
                facecolor=fig.get_facecolor(),
                transparent=True,
            )
        else:
            if extent is None:
                if len(ax) == 1:
                    if axis_off:
                        for ax in ax:
                            # if axis is turned off, constrain the saved
                            # figure's extent to the interior of the axis
                            extent = ax.get_window_extent().transformed(
                                fig.dpi_scale_trans.inverted()
                            )
                else:
                    extent = "tight"
            fig.savefig(
                path_filename,
                dpi=dpi,
                bbox_inches=extent,
                format=file_format,
                facecolor=fig.get_facecolor(),
                transparent=True,
            )
        log(
            "Saved the figure to disk in {:,.2f} seconds".format(
                time.time() - start_time
            )
        )

    # show the figure if specified
    if show:
        start_time = time.time()
        plt.show()
        # fig.show()
        log("Showed the plot in {:,.2f} seconds".format(time.time() - start_time))
    # if show=False, close the figure if close=True to prevent display
    elif close:
        plt.close()

    return fig, ax


def plot_energyseries(
    energy_series,
    kind="polygon",
    axis_off=True,
    cmap=None,
    fig_height=None,
    fig_width=6,
    show=True,
    view_angle=-60,
    save=False,
    close=False,
    dpi=300,
    file_format="png",
    color=None,
    axes=None,
    vmin=None,
    vmax=None,
    filename=None,
    timeStepsPerPeriod=24,
    **kwargs
):
    """
    Args:
        energy_series (EnergySeries):
        kind (str):
        axis_off (bool):
        cmap:
        fig_height (float):
        fig_width (float):
        show (bool):
        view_angle (float):
        save (bool):
        close (bool):
        dpi (int):
        file_format (str):
        color (str):
        axes:
        vmin (float):
        vmax (float):
        filename (str):
        timeStepsPerPeriod (int): The number of discrete timesteps which
            describe one period.
        **kwargs:
    """
    if energy_series.empty:
        warnings.warn(
            "The EnergyProgile you are attempting to plot is "
            "empty. Nothing has been displayed.",
            UserWarning,
        )
        return axes

    import matplotlib.pyplot as plt

    # noinspection PyUnresolvedReferences
    from mpl_toolkits.mplot3d import Axes3D

    if isinstance(energy_series.index, pd.MultiIndex):
        groups = energy_series.groupby(level=0)
        nax = len(groups)
    else:
        nax = 1
        groups = [("unnamed", energy_series)]

    if fig_height is None:
        fig_height = fig_width * nax

    # Set up plot
    fig, axes = plt.subplots(
        nax,
        1,
        subplot_kw=dict(projection="3d"),
        figsize=(fig_width, fig_height),
        dpi=dpi,
    )
    if not isinstance(axes, np.ndarray):
        axes = [axes]

    for ax, (name, profile) in zip(axes, groups):
        values = profile.values

        vmin = values.min() if vmin is None else vmin
        vmax = values.max() if vmax is None else vmax

        if kind == "polygon":
            import tsam.timeseriesaggregation as tsam

            z, _ = tsam.unstackToPeriods(profile, timeStepsPerPeriod=timeStepsPerPeriod)
            nrows, ncols = z.shape

            xs = z.columns
            zs = z.index.values

            verts = []
            for i in zs:
                ys = z.iloc[int(i), :]
                verts.append(_polygon_under_graph(xs, ys))

            _plot_poly_collection(
                ax,
                verts,
                zs,
                edgecolors=kwargs.get("edgecolors", None),
                facecolors=kwargs.get("facecolors", None),
                linewidths=kwargs.get("linewidths", None),
                cmap=cmap,
            )
        elif kind == "surface":
            import tsam.timeseriesaggregation as tsam

            z, _ = tsam.unstackToPeriods(profile, timeStepsPerPeriod=timeStepsPerPeriod)
            nrows, ncols = z.shape
            x = z.columns
            y = z.index.values

            x, y = np.meshgrid(x, y)
            _plot_surface(ax, x, y, z.values, cmap=cmap, **kwargs)
        elif kind == "contour":
            import tsam.timeseriesaggregation as tsam

            z, _ = tsam.unstackToPeriods(profile, timeStepsPerPeriod=timeStepsPerPeriod)
            nrows, ncols = z.shape
            x = z.columns
            y = z.index.values

            x, y = np.meshgrid(x, y)
            _plot_contour(ax, x, y, z.values, cmap=cmap, **kwargs)
        else:
            raise NameError('plot kind "{}" is not supported'.format(kind))

        if filename is None:
            filename = "unnamed"

        # set the extent of the figure
        ax.set_xlim3d(-1, ncols)
        ax.set_xlabel(kwargs.get("xlabel", "hour of day"))
        ax.set_ylim3d(-1, nrows)
        ax.set_ylabel(kwargs.get("ylabel", "day of year"))
        ax.set_zlim3d(vmin, vmax)
        z_label = "{} [{:~P}]".format(
            energy_series.name if energy_series.name is not None else "Z",
            energy_series.units,
        )
        ax.set_zlabel(z_label)

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
            ax.axis("off")
            ax.margins(0)
            ax.tick_params(which="both", direction="in")
            xaxis.set_visible(False)
            yaxis.set_visible(False)
            zaxis.set_visible(False)
            fig.canvas.draw()
        if view_angle is not None:
            ax.view_init(30, view_angle)
            ax.set_proj_type(kwargs.get("proj_type", "persp"))
            fig.canvas.draw()
    fig, axes = save_and_show(
        fig=fig,
        ax=axes,
        save=save,
        show=show,
        close=close,
        filename=filename,
        file_format=file_format,
        dpi=dpi,
        axis_off=axis_off,
        extent=None,
    )
    return fig, axes


def plot_energyseries_map(
    data,
    periodlength=24,
    subplots=False,
    vmin=None,
    vmax=None,
    axis_off=True,
    cmap="RdBu",
    fig_height=None,
    fig_width=6,
    show=True,
    view_angle=-60,
    save=False,
    close=False,
    dpi=300,
    file_format="png",
    color=None,
    ax=None,
    filename="untitled",
    extent="tight",
    sharex=False,
    sharey=False,
    layout=None,
    layout_type="vertical",
    **kwargs
):
    """
    Args:
        data (EnergySeries or EnergyDataFrame):
        periodlength:
        subplots:
        vmin:
        vmax:
        axis_off:
        cmap:
        fig_height:
        fig_width:
        show:
        view_angle:
        save:
        close:
        dpi:
        file_format:
        color:
        ax:
        filename:
        extent:
        sharex:
        sharey:
        layout:
        layout_type:
        **kwargs:
    """
    if fig_height is None:
        fig_height = fig_width / 3
    figsize = (fig_width, fig_height)

    if not ax:
        if subplots:
            if isinstance(data, EnergySeries):
                data = data.unstack(level=0)
            n = data.shape[1]
        else:
            n = 1
        fig, axes = plt.subplots(
            nrows=n, ncols=1, figsize=(fig_width, fig_height), dpi=dpi
        )
    else:
        fig = ax.get_figure()
        if figsize is not None:
            fig.set_size_inches(figsize)
        axes = ax

    stacked, timeindex = tsam.unstackToPeriods(copy.deepcopy(data), periodlength)
    cmap = plt.get_cmap(cmap)
    im = axes.imshow(
        stacked.values.T, interpolation="nearest", vmin=vmin, vmax=vmax, cmap=cmap
    )
    axes.set_aspect("auto")
    axes.set_ylabel("Hour")
    plt.xlabel("Day")

    # fig.subplots_adjust(right=1.1)
    cbar = fig.colorbar(im, ax=axes)
    cbar.set_label("{} [{:~P}]".format(data.name, data.units))

    fig, axes = save_and_show(
        fig, axes, save, show, close, filename, file_format, dpi, axis_off, extent
    )

    return fig, axes


def _plot_poly_collection(
    ax, verts, zs=None, color=None, cmap=None, vmin=None, vmax=None, **kwargs
):
    """
    Args:
        ax:
        verts:
        zs:
        color:
        cmap:
        vmin:
        vmax:
        **kwargs:
    """
    from matplotlib.collections import PolyCollection

    # if None in zs:
    #     zs = None

    # color=None overwrites specified facecolor/edgecolor with default color
    if color is not None:
        kwargs["color"] = color
    import matplotlib as mpl

    norm = mpl.colors.Normalize(vmin=vmin, vmax=vmax)

    poly = PolyCollection(verts, **kwargs)
    if zs is not None:
        poly.set_array(np.asarray(zs))
        poly.set_cmap(cmap)
        poly.set_clim(vmin, vmax)

    ax.add_collection3d(poly, zs=zs, zdir="y")
    # ax.autoscale_view()
    return poly


def _plot_surface(ax, x, y, z, cmap=None, **kwargs):
    """
    Args:
        ax:
        x:
        y:
        z:
        cmap:
        **kwargs:
    """
    if cmap is None:
        cmap = cm.gist_earth

    ls = LightSource(270, 45)
    # To use a custom hillshading mode, override the built-in shading and pass
    # in the rgb colors of the shaded surface calculated from "shade".
    rgb = ls.shade(z, cmap=cm.get_cmap(cmap), vert_exag=0.1, blend_mode="soft")
    surf = ax.plot_surface(
        x,
        y,
        z,
        rstride=1,
        cstride=1,
        facecolors=rgb,
        linewidth=0,
        antialiased=False,
        shade=False,
        **kwargs
    )
    return surf


def _plot_contour(ax, x, y, z, cmap=None, **kwargs):
    """
    Args:
        ax:
        x:
        y:
        z:
        cmap:
        **kwargs:
    """
    if cmap is None:
        cmap = cm.gist_earth
    surf = ax.contour3D(x, y, z, 150, cmap=cmap, **kwargs)
    return surf


def _polygon_under_graph(xlist, ylist):
    """Construct the vertex list which defines the polygon filling the space
    under the (xlist, ylist) line graph. Assumes the xs are in ascending order.

    Args:
        xlist:
        ylist:
    """
    return [(xlist[0], 0.0), *zip(xlist, ylist), (xlist[-1], 0.0)]


EnergySeries.plot3d.__doc__ = plot_energyseries.__doc__
EnergySeries.plot2d.__doc__ = plot_energyseries_map.__doc__
