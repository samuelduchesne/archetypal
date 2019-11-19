################################################################################
# Module: plot.py
# Description: Plot energy profiles, spatial geometries, networks, and routes
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################
# OSMnx
#
# Copyright (c) 2019 Geoff Boeing https://geoffboeing.com/
#
# Part of the following code is a derivative work of the code from the OSMnx
# project, which is licensed MIT License. This code therefore is also
# licensed under the terms of the The MIT License (MIT).
################################################################################

import os
import time
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import cm
from matplotlib.colors import LightSource

from archetypal import settings, log


def save_and_show(
    fig, ax, save, show, close, filename, file_format, dpi, axis_off, extent
):
    """Save a figure to disk and show it, as specified.

    Args:
        extent (str or `~matplotlib.transforms.Bbox`, optional): Bbox in
            inches. Only the given portion of the figure is saved. If
            'tight', try to figure out the tight bbox of the figure. If None,
            use savefig.bbox
        fig (matplotlib.figure.Figure): the figure
        ax (matplotlib.axes.Axes): the axes
        save (bool): whether to save the figure to disk or not
        show (bool): whether to display the figure or not
        close (bool): close the figure (only if show equals False) to prevent
            display
        filename (string): the name of the file to save
        file_format (str): the format of the file to save (e.g., 'jpg',
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
        path_filename = os.path.join(
            settings.imgs_folder, os.extsep.join([filename, file_format])
        )

        if not isinstance(ax, (np.ndarray, list)):
            ax = [ax]
        if file_format == "svg":
            fig.patch.set_alpha(0.0)
            fig.savefig(
                path_filename,
                bbox_inches=extent,
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
                    pass
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


def plot_energyprofile(
    energyprofile,
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
    **kwargs
):
    """

    Args:
        energyprofile:
        axis_off:
        cmap:
        fig_height:
        fig_width:
        show:
        save:
        close:
        dpi:
        file_format:
        color:
        axes:
        vmin:
        vmax:
        filename:
        **kwargs:

    Returns:

    """
    if energyprofile.empty:
        warnings.warn(
            "The EnergySeries you are attempting to plot is "
            "empty. Nothing has been displayed.",
            UserWarning,
        )
        return axes

    import matplotlib.pyplot as plt

    # noinspection PyUnresolvedReferences
    from mpl_toolkits.mplot3d import Axes3D

    if isinstance(energyprofile.index, pd.MultiIndex):
        groups = energyprofile.groupby(level=0)
        nax = len(groups)
    else:
        nax = 1
        groups = [("unnamed", energyprofile)]

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

        facecolor = kwargs.pop("facecolor", None)
        if color is not None:
            facecolor = color

        if kind == "polygon":
            z = values.reshape(365, 24)
            nrows, ncols = z.shape
            xs = np.linspace(0, 23, ncols)
            # y = np.linspace(0, 364, nrows)
            # The ith polygon will appear on the plane y = zs[i]
            zs = np.linspace(0, 364, nrows)
            verts = []
            for i in zs:
                ys = z[int(i), :]
                verts.append(polygon_under_graph(xs, ys))

            plot_poly_collection(
                ax,
                verts,
                zs,
                edgecolors=kwargs.get("edgecolors", None),
                facecolors=kwargs.get("facecolors", None),
                linewidths=kwargs.get("linewidths", None),
                cmap=cmap,
            )
        elif kind == "surface":
            z = values.reshape(365, 24)
            nrows, ncols = z.shape
            x = np.linspace(1, 24, ncols)
            y = np.linspace(1, 365, nrows)
            x, y = np.meshgrid(x, y)
            plot_surface(ax, x, y, z, cmap=cmap, **kwargs)
        else:
            raise NameError('plot kind "{}" is not supported'.format(kind))

        if filename is None:
            filename = "unnamed"

        # set the extent of the figure
        ax.set_xlim3d(-1, 24)
        ax.set_xlabel("X")
        ax.set_ylim3d(-1, 365)
        ax.set_ylabel("Y")
        ax.set_zlim3d(vmin, vmax)
        ax.set_zlabel("Z")

        # configure axis appearance
        xaxis = ax.xaxis
        yaxis = ax.yaxis
        zaxis = ax.zaxis

        xaxis.get_major_formatter().set_useOffset(False)
        yaxis.get_major_formatter().set_useOffset(False)
        zaxis.get_major_formatter().set_useOffset(False)

        # if axis_off, turn off the axis display set the margins to zero and
        # point
        # the ticks in so there's no space around the plot
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


def plot_poly_collection(
    ax, verts, zs=None, color=None, cmap=None, vmin=None, vmax=None, **kwargs
):
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


def plot_surface(ax, x, y, z, cmap=None, **kwargs):
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
    )
    return surf


def polygon_under_graph(xlist, ylist):
    """Construct the vertex list which defines the polygon filling the space
    under
    the (xlist, ylist) line graph.  Assumes the xs are in ascending order."""
    return [(xlist[0], 0.0), *zip(xlist, ylist), (xlist[-1], 0.0)]
