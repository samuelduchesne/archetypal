import matplotlib.pyplot as plt
from pandas import DataFrame, Series, DatetimeIndex

from archetypal import EnergySeries, settings
from archetypal.energyseries import plot_energyseries_map, save_and_show


class EnergyDataFrame(DataFrame):
    """An EnergyDataFrame object is a pandas.DataFrame that has energy related
    data. In addition to the standard DataFrame constructor arguments,
    EnergyDataFrame also accepts the following keyword arguments:


    """

    _metadata = [
        "profile_type",
        "base_year",
        "frequency",
        "units",
        "sort_values",
        "to_units",
    ]

    def __init__(self, *args, **kwargs):
        from_units = kwargs.pop("units", None)
        super(EnergyDataFrame, self).__init__(*args, **kwargs)
        self.from_units = from_units
        if from_units is not None:
            self.set_unit(from_units, inplace=True)

    def set_unit(self, from_unit, inplace):
        ureg = settings.unit_registry

        if inplace:
            frame = self
        else:
            frame = self.copy()

        self.from_units = ureg.parse_expression(from_unit)

        if not inplace:
            return frame

    def plot2d(self, **kwargs):
        return plot_energydataframe_map(self, **kwargs)

    @property
    def _constructor(self):
        return EnergyDataFrame

    @property
    def nseries(self):
        if self._data.ndim == 1:
            return 1
        else:
            return self._data.shape[0]

    def __getitem__(self, key):
        """
        return an EnergySeries or an EnergyDataFrame with propagated metadata.
        """
        result = super(EnergyDataFrame, self).__getitem__(key)
        if isinstance(result, Series):
            result.__class__ = EnergySeries
        elif isinstance(result, DataFrame):
            result.__class__ = EnergyDataFrame
        return result.__finalize__(self)

    def stack(self, level=-1, dropna=True):
        from pandas.core.reshape.reshape import stack, stack_multiple

        if isinstance(level, (tuple, list)):
            result = stack_multiple(self, level, dropna=dropna)
            return result.__finalize__(self)
        else:
            result = stack(self, level, dropna=dropna)
            return result.__finalize__(self)

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
        """uses tsam"""
        try:
            import tsam.timeseriesaggregation as tsam
        except ImportError:
            raise ImportError("tsam is required for discretize_tsam()")
        if not isinstance(self.index, DatetimeIndex):
            raise TypeError("To use tsam, index of series must be a " "DateTimeIndex")
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
        results = EnergyDataFrame(results)
        results.__dict__["agg"] = agg
        return results.__finalize__(self)


def plot_energydataframe_map(
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
    sharex=True,
    sharey=True,
    layout=None,
    layout_type="vertical",
    **kwargs
):
    if fig_height is None:
        fig_height = fig_width / 3
    figsize = (fig_width, fig_height)
    nseries = data.nseries
    fig, axes = _setup_subplots(
        subplots, nseries, sharex, sharey, figsize, ax, layout, layout_type
    )
    cols = data.columns
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
            **kwargs
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
    from pandas.plotting._tools import _subplots, _flatten

    if subplots:
        fig, axes = _subplots(
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

    axes = _flatten(axes)

    return fig, axes
