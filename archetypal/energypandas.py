"""EnergyPandas module.

An extension of pandas DataFrames and Series for Energy modelers.
"""

import copy
import os
import time
import warnings
from datetime import timedelta

import tsam.timeseriesaggregation as tsam
from matplotlib import cm
from matplotlib import pyplot as plt
from matplotlib.colors import LightSource, TwoSlopeNorm
from numpy import asarray, meshgrid, ndarray
from pandas.core.frame import DataFrame
from pandas.core.generic import NDFrame
from pandas.core.indexes.datetimes import DatetimeIndex, date_range
from pandas.core.indexes.multi import MultiIndex
from pandas.core.reshape.pivot import pivot_table
from pandas.core.series import Series
from pandas.core.tools.datetimes import to_datetime
from pandas.plotting._matplotlib.tools import flatten_axes, create_subplots
from pint import Quantity, Unit
from sklearn import preprocessing

import archetypal.settings as settings
from archetypal.utils import log


class EnergySeries(Series):
    """A Series object designed to store energy related data."""

    _metadata = [
        "bin_edges_",
        "bin_scaling_factors_",
        "base_year",
        "frequency",
        "units",
        "name",
    ]

    @property
    def _constructor(self):
        return EnergySeries

    @property
    def _constructor_expanddim(self):
        def f(*args, **kwargs):
            # adapted from https://github.com/pandas-dev/pandas/issues/19850#issuecomment-367934440
            return EnergyDataFrame(*args, **kwargs).__finalize__(self, method="inherit")

        f._get_axis_number = super(EnergySeries, self)._get_axis_number

        return f

    def __init__(
        self,
        data=None,
        index=None,
        dtype=None,
        name=None,
        copy=False,
        fastpath=False,
        units=None,
        **kwargs,
    ):
        """Initiate EnergySeries.

        Args:
            data (array-like, Iterable, dict, or scalar value): Contains data stored
                in Series.
            index (array-like or Index (1d)):  Values must be hashable and have the
                same length as `data`. Non-unique index values are allowed. Will
                default to RangeIndex (0, 1, 2, ..., n) if not provided. If both a
                dict and index sequence are used, the index will override the keys
                found in the dict.
            dtype (str, numpy.dtype, or ExtensionDtype, optional): Data type for the
                output Series. If not specified, this will be inferred from `data`.
                See the :ref:`user guide <basics.dtypes>` for more usages.
            name (str, optional): The name to give to the Series.
            copy (bool): Copy input data. Defaults to False
            fastpath (bool): Defaults to False
            units (:obj:`str`, optional): The series units. Parsed as Pint units.
        """
        super(EnergySeries, self).__init__(
            data=data, index=index, dtype=dtype, name=name, copy=copy, fastpath=fastpath
        )
        self.bin_edges_ = None
        self.bin_scaling_factors_ = None
        self.units = units

        for k, v in kwargs.items():
            EnergySeries._metadata.append(k)
            setattr(EnergySeries, k, v)

    def __finalize__(self, other, method=None, **kwargs):
        """Propagate metadata from other to self."""
        if isinstance(other, NDFrame):
            for name in other.attrs:
                self.attrs[name] = other.attrs[name]
            # For subclasses using _metadata. Set known attributes and update list.
            for name in other._metadata:
                try:
                    object.__setattr__(self, name, getattr(other, name))
                except AttributeError:
                    pass
                if name not in self._metadata:
                    self._metadata.append(name)
        return self

    def __repr__(self):
        """Adds units to repr"""
        result = super(EnergySeries, self).__repr__()
        return result + f", units:{self.units:~P}"

    @classmethod
    def with_timeindex(
        cls,
        data,
        base_year=2018,
        frequency="H",
        index=None,
        dtype=None,
        name=None,
        copy=False,
        fastpath=False,
        units=None,
        **kwargs,
    ):
        # handle DateTimeIndex
        es = cls(
            data=data,
            index=index,
            dtype=dtype,
            name=name,
            copy=copy,
            fastpath=fastpath,
            units=units,
            **kwargs,
        )
        start_date = str(base_year) + "0101"
        newindex = date_range(start=start_date, freq=frequency, periods=len(es))
        es.index = newindex
        return es

    @property
    def units(self):
        return self._units

    @units.setter
    def units(self, value):
        if isinstance(value, str):
            self._units = settings.unit_registry.parse_expression(value).units
        elif isinstance(value, (Unit, Quantity)):
            self._units = value
        elif value is None:
            self._units = settings.unit_registry.parse_expression(value).units
        else:
            raise TypeError(f"Unit of type {type(value)}")

    @classmethod
    def from_reportdata(
        cls,
        df,
        name=None,
        base_year=2018,
        units=None,
        normalize=False,
        sort_values=False,
        ascending=False,
        to_units=None,
        agg_func="sum",
    ):
        """Create a.

        Args:
            df (DataFrame):
            name:
            base_year:
            units:
            normalize (bool): Normalize between 0 and 1.
            sort_values:
            ascending:
            to_units (str): Convert original values to this unit. Dimensionality
                check performed by `pint`.
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
        index = to_datetime(
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
        index = DatetimeIndex(index)
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
        # Since we create the index, don't need to use .with_timeindex() constructor
        energy_series = cls(
            grouped_Data.values,
            name=name,
            units=units,
            index=grouped_Data.index,
            base_year=base_year,
        )
        if normalize:
            energy_series.normalize(inplace=True)
        if sort_values:
            energy_series.sort_values(ascending=ascending, inplace=True)
        if to_units and not normalize:
            energy_series.to_units(to_units, inplace=True)
        return energy_series

    def to_units(self, to_units=None, inplace=False):
        """returns the multiplier to convert units

        Args:
            to_units (str, pint.Unit):
            inplace:
        """
        cdata = settings.unit_registry.Quantity(self.values, self.units).to(to_units).m
        if inplace:
            self[:] = cdata
            self.units = to_units
        else:
            # create new instance using constructor
            result = self._constructor(data=cdata, index=self.index, copy=False)
            # Copy metadata over
            result.__finalize__(self)
            result.units = to_units
            return result

    def normalize(self, inplace=False):
        """Returns a normalized EnergySeries

        Args:
            inplace:
        """
        x = self.values  # returns a numpy array
        min_max_scaler = preprocessing.MinMaxScaler()
        x_scaled = min_max_scaler.fit_transform(x.reshape(-1, 1)).ravel()
        if inplace:
            # replace whole data with array
            self[:] = x_scaled
            # change units to dimensionless
            self.units = settings.unit_registry.dimensionless
        else:
            # create new instance using constructor
            result = self._constructor(data=x_scaled, index=self.index, copy=False)
            # Copy metadata over
            result.__finalize__(self)
            return result

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

    def discretize_tsam(self, inplace=False, **kwargs):
        """Clusters time series data to typical periods. See
        :class:`tsam.timeseriesaggregation.TimeSeriesAggregation` for more info.

        Returns:
            EnergySeries:
        """
        try:
            import tsam.timeseriesaggregation as tsam
        except ImportError:
            raise ImportError("tsam is required for discretize_tsam()")
        if not isinstance(self.index, DatetimeIndex):
            raise TypeError("To use tsam, index of series must be a " "DateTimeIndex")

        timeSeries = self.to_frame()
        agg = tsam.TimeSeriesAggregation(timeSeries, **kwargs)

        agg.createTypicalPeriods()
        result = agg.predictOriginalData()
        if inplace:
            self.loc[:] = result.values.ravel()
        else:
            # create new instance using constructor
            result = self._constructor(
                data=result.values.ravel(), index=self.index, copy=False
            )
            # Copy metadata over
            result.__finalize__(self)
            return result

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

    @property
    def p_max(self):
        if isinstance(self.index, MultiIndex):
            return self.groupby(level=0).max()
        else:
            return self.max()

    @property
    def monthly(self):
        if isinstance(self.index, DatetimeIndex):
            data = self.resample("M").mean()
            return self._constructor(
                data, index=data.index, frequency="M", units=self.units
            )
        else:
            return None

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

        if not isinstance(ax, (ndarray, list)):
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
    **kwargs,
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

    if isinstance(energy_series.index, MultiIndex):
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
    if not isinstance(axes, ndarray):
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

            x, y = meshgrid(x, y)
            _plot_surface(ax, x, y, z.values, cmap=cmap, **kwargs)
        elif kind == "contour":
            import tsam.timeseriesaggregation as tsam

            z, _ = tsam.unstackToPeriods(profile, timeStepsPerPeriod=timeStepsPerPeriod)
            nrows, ncols = z.shape
            x = z.columns
            y = z.index.values

            x, y = meshgrid(x, y)
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
    vcenter=None,
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
    **kwargs,
):
    """
    Args:
        data (EnergySeries or EnergyDataFrame):
        periodlength:
        subplots:
        vmin (float): The data value that defines ``0.0`` in the normalization.
            Defaults to the min value of the dataset.
        vmax (float): The data value that defines ``1.0`` in the normalization.
            Defaults to the the max value of the dataset.
        vcenter (float): The data value that defines ``0.5`` in the normalization.
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
    if vcenter is not None:
        norm = TwoSlopeNorm(vcenter, vmin=vmin, vmax=vmax)
    else:
        norm = None
    im = axes.imshow(
        stacked.values.T,
        interpolation="nearest",
        vmin=vmin,
        vmax=vmax,
        cmap=cmap,
        norm=norm,
    )
    axes.set_aspect("auto")
    axes.set_ylabel("Hour of day")
    axes.set_xlabel("Day of year")
    plt.title(f"{data.name}")

    # fig.subplots_adjust(right=1.1)
    cbar = fig.colorbar(im, ax=axes)
    cbar.set_label(f"[{data.units:~P}]")

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
        poly.set_array(asarray(zs))
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
        **kwargs,
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


class EnergyDataFrame(DataFrame):
    """An EnergyDataFrame object is a pandas.DataFrame that has energy related
    data. In addition to the standard DataFrame constructor arguments,
    EnergyDataFrame also accepts the following keyword arguments:


    """

    # temporary properties
    _internal_names = DataFrame._internal_names
    _internal_names_set = set(_internal_names)

    # normal properties
    _metadata = ["units", "name"]

    @property
    def _constructor(self):
        return EnergyDataFrame

    @property
    def _constructor_sliced(self):
        # return EnergySeries
        def f(*args, **kwargs):
            # adapted from https://github.com/pandas-dev/pandas/issues/13208#issuecomment-326556232
            return EnergySeries(*args, **kwargs).__finalize__(self, method="inherit")

        return f

    def __init__(
        self,
        data,
        units=None,
        index=None,
        columns=None,
        dtype=None,
        copy=True,
        **kwargs,
    ):
        super(EnergyDataFrame, self).__init__(
            data, index=index, columns=columns, dtype=dtype, copy=copy
        )
        self.units = units
        for k, v in kwargs.items():
            self._metadata.append(k)
            setattr(self, k, v)

    def __finalize__(self, other, method=None, **kwargs):
        """Propagate metadata from other to self."""
        if isinstance(other, NDFrame):
            for name in other.attrs:
                self.attrs[name] = other.attrs[name]
            # For subclasses using _metadata. Set known attributes and update list.
            for name in other._metadata:
                try:
                    object.__setattr__(self, name, getattr(other, name))
                except AttributeError:
                    pass
                if name not in self._metadata:
                    self._metadata.append(name)
        return self

    @classmethod
    def from_reportdata(
        cls,
        df,
        name=None,
        base_year=2018,
        units=None,
        normalize=False,
        sort_values=False,
        to_units=None,
    ):
        """From a ReportData DataFrame"""
        # get data
        units = [units] if units else set(df.Units)
        if len(units) > 1:
            raise ValueError("The DataFrame contains mixed units: {}".format(units))
        else:
            units = next(iter(units), None)
        # group data by index value (level=0) using the agg_func
        grouped_Data = pivot_table(
            df, index="TimeIndex", columns=["KeyValue"], values=["Value"]
        ).droplevel(axis=1, level=0)
        df = pivot_table(
            df,
            index="TimeIndex",
            columns=None,
            values=["Month", "Day", "Hour", "Minute", "Interval"],
        )
        index = to_datetime(
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
        index = DatetimeIndex(index)
        grouped_Data.index = index
        # Since we create the index, use_timeindex must be false
        edf = cls(grouped_Data, units=units, index=grouped_Data.index, name=name)
        if to_units:
            edf.to_units(to_units=to_units, inplace=True)
        if normalize:
            edf.normalize(inplace=True)
        if sort_values:
            edf.sort_values(sort_values, inplace=True)
        return edf

    @property
    def units(self):
        return self._units

    @units.setter
    def units(self, value):
        if isinstance(value, str):
            self._units = settings.unit_registry.parse_expression(value).units
        elif isinstance(value, (Unit, Quantity)):
            self._units = value
        elif value is None:
            self._units = settings.unit_registry.parse_expression(value).units
        else:
            raise TypeError(f"Unit of type {type(value)}")

    def to_units(self, to_units=None, inplace=False):
        """returns the multiplier to convert units

        Args:
            to_units (str or pint.Unit):
            inplace:
        """
        cdata = settings.unit_registry.Quantity(self.values, self.units).to(to_units).m
        if inplace:
            self[:] = cdata
            self.units = to_units
        else:
            # create new instance using constructor
            result = self._constructor(
                data=cdata, index=self.index, columns=self.columns, copy=False
            )
            # Copy metadata over
            result.__finalize__(self)
            result.units = to_units
            return result

    def normalize(self, inplace=False):
        x = self.values  # returns a numpy array
        min_max_scaler = preprocessing.MinMaxScaler()
        x_scaled = min_max_scaler.fit_transform(x)
        if inplace:
            # replace whole data with array
            self[:] = x_scaled
            # change units to dimensionless
            self.units = settings.unit_registry.dimensionless
        else:
            # create new instance using constructor
            result = self._constructor(
                data=x_scaled, index=self.index, columns=self.columns, copy=False
            )
            # Copy metadata over
            result.__finalize__(self)
            return result

    def plot2d(self, **kwargs):
        return plot_energydataframe_map(self, **kwargs)

    @property
    def nseries(self):
        if self._data.ndim == 1:
            return 1
        else:
            return self._data.shape[0]

    def discretize_tsam(self, inplace=False, **kwargs):
        """Clusters time series data to typical periods. See
        :class:`tsam.timeseriesaggregation.TimeSeriesAggregation` for more info.

        Returns:
            EnergyDataFrame:
        """
        try:
            import tsam.timeseriesaggregation as tsam
        except ImportError:
            raise ImportError("tsam is required for discretize_tsam()")
        if not isinstance(self.index, DatetimeIndex):
            raise TypeError("To use tsam, index of series must be a " "DateTimeIndex")
        timeSeries = self.copy()
        agg = tsam.TimeSeriesAggregation(timeSeries, **kwargs)

        agg.createTypicalPeriods()
        result = agg.predictOriginalData()
        if inplace:
            self.loc[:] = result.values
        else:
            # create new instance using constructor
            result = self._constructor(
                data=result.values, index=self.index, columns=self.columns, copy=False
            )
            # Copy metadata over
            result.__finalize__(self)
            return result

    discretize_tsam.__doc__ = tsam.TimeSeriesAggregation.__init__.__doc__


def plot_energydataframe_map(
    data,
    periodlength=None,
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
    sharex=True,
    sharey=True,
    layout=None,
    layout_type="vertical",
    **kwargs,
):
    nseries = data.nseries
    if fig_height is None:
        fig_height = fig_width / 3 * nseries
    figsize = (fig_width, fig_height)
    fig, axes = _setup_subplots(
        subplots, nseries, sharex, sharey, figsize, ax, layout, layout_type
    )
    cols = data.columns
    if periodlength is None:
        import pandas as pd

        periodlength = (
            24 * 1 / (pd.to_timedelta(data.index.inferred_freq).seconds / 3600)
        )
    for ax, col in zip(axes, cols):
        plot_energyseries_map(
            data[col],
            periodlength=periodlength,
            subplots=subplots,
            vmin=vmin,
            vmax=vmax,
            axis_off=axis_off,
            cmap=cmap,
            fig_height=fig_height,
            fig_width=fig_width,
            show=False,
            save=False,
            close=False,
            dpi=dpi,
            file_format=file_format,
            color=color,
            ax=ax,
            filename=filename,
            extent=extent,
            sharex=sharex,
            sharey=sharey,
            layout=layout,
            layout_type=layout_type,
            **kwargs,
        )

    fig, axes = save_and_show(
        fig, axes, save, show, close, filename, file_format, dpi, axis_off, extent
    )

    return fig, axes


def _setup_subplots(
    subplots,
    nseries,
    sharex=False,
    sharey=False,
    figsize=None,
    ax=None,
    layout=None,
    layout_type="vertical",
):
    """prepares the subplots"""

    if subplots:
        fig, axes = create_subplots(
            naxes=nseries,
            sharex=sharex,
            sharey=sharey,
            figsize=figsize,
            ax=ax,
            layout=layout,
            layout_type=layout_type,
        )
    else:
        if ax is None:
            fig = plt.figure(figsize=figsize)
            axes = fig.add_subplot(111)
        else:
            fig = ax.get_figure()
            if figsize is not None:
                fig.set_size_inches(figsize)
            axes = ax

    axes = flatten_axes(axes)

    return fig, axes
