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

import numpy as np

from archetypal import settings
from archetypal.utils import log


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
    import matplotlib.pyplot as plt

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
