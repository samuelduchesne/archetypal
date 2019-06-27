################################################################################
# Module: cli.py
# Description: Implements archetypal functions as Command Line Interfaces
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################
import os

import click

import archetypal
from archetypal import settings, cd

CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])


class Config(object):
    def __init__(self):
        self.data_folder = settings.data_folder,
        self.logs_folder = settings.logs_folder,
        self.imgs_folder = settings.imgs_folder,
        self.cache_folder = settings.cache_folder,
        self.use_cache = settings.use_cache,
        self.log_file = settings.log_file,
        self.log_console = settings.log_console,
        self.log_level = settings.log_level,
        self.log_name = settings.log_name,
        self.log_filename = settings.log_filename,
        self.useful_idf_objects = settings.useful_idf_objects,
        self.umitemplate = settings.umitemplate,
        self.trnsys_default_folder = settings.trnsys_default_folder


pass_config = click.make_pass_decorator(Config, ensure=True)


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option('--data-folder', type=click.Path(),
              help='where to save and load data files',
              default=settings.data_folder)
@click.option('--logs-folder', type=click.Path(),
              help='where to write the log files',
              default=settings.logs_folder)
@click.option('--imgs-folder', type=click.Path(),
              help='where to save figures',
              default=settings.imgs_folder)
@click.option('--cache-folder', type=click.Path(),
              help='where to save the simluation results',
              default=settings.cache_folder)
@click.option('--use-cache', is_flag=True,
              help='Use a local cache to save/retrieve many of '
                   'archetypal outputs such as EnergyPlus simulation results',
              default=settings.use_cache)
@click.option('--log-file', is_flag=True,
              help='save log output to a log file in logs_folder',
              default=settings.log_file)
@click.option('--log-console', '--verbose', '-v', is_flag=True,
              default=settings.log_console,
              help='print log output to the console')
@click.option('--log-level', type=click.INT,
              help='CRITICAL=50, ERROR=40, WARNING=30, INFO=20, DEBUG=10',
              default=settings.log_level)
@click.option('--log-name', help='name of the logger',
              default=settings.log_name)
@click.option('--log-filename', help='name of the log file',
              default=settings.log_filename)
@click.option('--trnsys-default-folder', type=click.Path(),
              help='root folder of TRNSYS install',
              default=settings.trnsys_default_folder)
@pass_config
def cli(config, data_folder, logs_folder, imgs_folder, cache_folder,
        use_cache, log_file, log_console, log_level, log_name, log_filename,
        trnsys_default_folder):
    """Retrieve, construct, simulate, and analyse building templates"""
    config.data_folder = data_folder
    config.logs_folder = logs_folder
    config.imgs_folder = imgs_folder
    config.cache_folder = cache_folder
    config.use_cache = use_cache
    config.log_file = log_file
    config.log_console = log_console
    config.log_level = log_level
    config.log_name = log_name
    config.log_filename = log_filename
    config.trnsys_default_folder = trnsys_default_folder
    archetypal.config(**config.__dict__)


@cli.command()
@click.argument('idf-file', type=click.Path(exists=True))
@click.argument('output-folder', type=click.Path(exists=True), required=False,
                default=".")
@click.option('--return-idf', '-i', is_flag=True, default=False,
              help='Save modified IDF file to output_folder, and return path to the file in the console')
@click.option('--return_t3d', '-t', is_flag=True, default=False,
              help='Return T3D file path in the console')
@click.option('--return_dck', '-d', is_flag=True, default=False,
              help='Generate dck file and save to output_folder, and return path to the file in the console')
@click.option('--window-lib', type=click.Path(), default=None,
              help='Path of the window library (from Berkeley Lab)')
@click.option('--trnsidf-exe', type=click.Path(),
              help='Path to trnsidf.exe',
              default=os.path.join(
                  settings.trnsys_default_folder,
                  r"Building\trnsIDF\trnsidf.exe"))
@click.option('--template', type=click.Path(),
              default=settings.path_template_d18,
              help='Path to d18 template file')
@click.option('--log-clear-names', is_flag=True, default=False,
              help='Do not print log of "clear_names" (equivalence between old and new names) in the console')
@click.option('--window', nargs=4, type=float, default=(2.2, 0.64, 0.8, 0.05),
              help="Specify window properties <u_value> <shgc> <t_vis> <tolerance>. Default = 2.2 0.64 0.8 0.05")
@click.option('--ordered', is_flag=True,
              help="sort idf object names")
@click.option('--nonum', is_flag=True, default=False,
              help="Do not renumber surfaces")
@click.option('--batchjob', '-N', is_flag=True, default=False,
              help="BatchJob Modus")
@click.option('--geofloor', type=float, default=0.6,
              help="Generates GEOSURF values for distributing; direct solar "
                   "radiation where `geo_floor` % is directed to the floor, "
                   "the rest; to walls/windows. Default = 0.6")
@click.option('--refarea', is_flag=True, default=False,
              help="Upadtes floor reference area of airnodes")
@click.option('--volume', is_flag=True, default=False,
              help="Upadtes volume of airnodes")
@click.option('--capacitance', is_flag=True, default=False,
              help="Upadtes capacitance of airnodes")
def convert(idf_file, window_lib, return_idf, return_t3d,
            return_dck, output_folder, trnsidf_exe, template, log_clear_names,
            window,
            ordered, nonum, batchjob, geofloor, refarea, volume, capacitance):
    """Convert regular IDF file (EnergyPlus) to TRNBuild file (TRNSYS)
    The output folder path defaults to the working directory. Equivalent to '.' """
    u_value, shgc, t_vis, tolerance = window
    window_kwds = {'u_value': u_value, 'shgc': shgc, 't_vis': t_vis,
                   'tolerance': tolerance}
    with cd(output_folder):
        paths = archetypal.convert_idf_to_trnbuild(idf_file, window_lib,
                                                   return_idf, True,
                                                   return_t3d, return_dck,
                                                   output_folder, trnsidf_exe,
                                                   template,
                                                   log_clear_names=log_clear_names,
                                                   **window_kwds,
                                                   ordered=ordered,
                                                   nonum=nonum, N=batchjob,
                                                   geo_floor=geofloor,
                                                   refarea=refarea,
                                                   volume=volume,
                                                   capacitance=capacitance)
    # Print path of output files in console
    if paths:
        click.echo('Here are the paths to the different output files: ')

        for path in paths:
            if 'MODIFIED' in path:
                click.echo(
                    'Path to the modified IDF file: {}'.format(path))
            elif 'b18' in path:
                click.echo('Path to the BUI file: {}'.format(path))
            elif 'dck' in path:
                click.echo('Path to the DCK file: {}'.format(path))
            else:
                click.echo('Path to the T3D file: {}'.format(path))


@cli.command()
def reduce():
    pass
