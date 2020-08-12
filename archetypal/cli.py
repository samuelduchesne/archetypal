################################################################################
# Module: cli.py
# Description: Implements archetypal functions as Command Line Interfaces
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################
import logging
import os
import time
from glob import glob

import click
from path import Path

from archetypal import (
    settings,
    convert_idf_to_trnbuild,
    get_eplus_dirs,
    parallel_process,
    UmiTemplateLibrary,
    config,
    log,
    idf_version_updater,
    timeit,
    EnergyPlusProcessError,
    __version__,
    ep_version,
    docstring_parameter,
)

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


class CliConfig(object):
    def __init__(self):
        self.data_folder = settings.data_folder
        self.logs_folder = settings.logs_folder
        self.imgs_folder = settings.imgs_folder
        self.cache_folder = settings.cache_folder
        self.use_cache = settings.use_cache
        self.log_file = settings.log_file
        self.log_console = settings.log_console
        self.log_level = settings.log_level
        self.log_name = settings.log_name
        self.log_filename = settings.log_filename
        self.useful_idf_objects = settings.useful_idf_objects
        self.umitemplate = settings.umitemplate
        self.trnsys_default_folder = settings.trnsys_default_folder
        self.ep_version = settings.ep_version


pass_config = click.make_pass_decorator(CliConfig, ensure=True)


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option(
    "--data-folder",
    type=click.Path(),
    help="where to save and load data files",
    default=settings.data_folder,
)
@click.option(
    "--logs-folder",
    type=click.Path(),
    help="where to write the log files",
    default=settings.logs_folder,
)
@click.option(
    "--imgs-folder",
    type=click.Path(),
    help="where to save figures",
    default=settings.imgs_folder,
)
@click.option(
    "--cache-folder",
    type=click.Path(),
    help="where to save the simluation results",
    default=settings.cache_folder,
)
@click.option(
    "-c",
    "--use-cache",
    is_flag=True,
    default=False,
    help="Use a local cache to save/retrieve many of "
    "archetypal outputs such as EnergyPlus simulation results",
)
@click.option(
    "-l",
    "--log-file",
    "log_file",
    is_flag=True,
    help="save log output to a log file in logs_folder",
    default=settings.log_file,
)
@click.option(
    "--silent",
    "-s",
    "log_console",
    is_flag=True,
    default=True,
    help="print log output to the console",
)
@click.option(
    "--log-level",
    type=click.INT,
    help="CRITICAL=50, ERROR=40, WARNING=30, INFO=20, DEBUG=10",
    default=settings.log_level,
)
@click.option("--log-name", help="name of the logger", default=settings.log_name)
@click.option(
    "--log-filename", help="name of the log file", default=settings.log_filename
)
@click.option(
    "--trnsys-default-folder",
    type=click.Path(),
    help="root folder of TRNSYS install",
    default=settings.trnsys_default_folder,
)
@click.option(
    "--ep_version",
    type=click.STRING,
    default=settings.ep_version,
    help='the EnergyPlus version to use. eg. "{}"'.format(settings.ep_version),
)
@click.option(
    "-d",
    "--debug",
    is_flag=True,
    default=False,
    help="Will break on any exception. Useful when debugging",
)
@pass_config
def cli(
    cli_config,
    data_folder,
    logs_folder,
    imgs_folder,
    cache_folder,
    use_cache,
    log_file,
    log_console,
    log_level,
    log_name,
    log_filename,
    trnsys_default_folder,
    ep_version,
    debug,
):
    """archetypal: Retrieve, construct, simulate, convert and analyse building
    simulation templates

    Visit archetypal.readthedocs.io for the online documentation.

    """
    cli_config.data_folder = data_folder
    cli_config.logs_folder = logs_folder
    cli_config.imgs_folder = imgs_folder
    cli_config.cache_folder = cache_folder
    cli_config.use_cache = use_cache
    cli_config.log_file = log_file
    cli_config.log_console = log_console
    cli_config.log_level = log_level
    cli_config.log_name = log_name
    cli_config.log_filename = log_filename
    cli_config.trnsys_default_folder = trnsys_default_folder
    cli_config.ep_version = ep_version
    cli_config.debug = debug
    # apply new config params
    config(**cli_config.__dict__)


@cli.command()
@click.argument("idf_file", type=click.Path(exists=True))
@click.argument("weather_file", type=click.Path(exists=True))
@click.argument(
    "output_folder", type=click.Path(exists=True), required=False, default="."
)
@click.option(
    "--return_idf",
    "-i",
    is_flag=True,
    default=False,
    help="Save modified IDF file to output_folder, and return path "
    "to the file in the console",
)
@click.option(
    "--return_t3d",
    "-t",
    is_flag=True,
    default=False,
    help="Return T3D file path in the console",
)
@click.option(
    "--return_dck",
    "-d",
    is_flag=True,
    default=False,
    help="Generate dck file and save to output_folder, and return "
    "path to the file in the console",
)
@click.option(
    "--window_lib",
    type=click.Path(),
    default=None,
    help="Path of the window library (from Berkeley Lab)",
)
@click.option(
    "--trnsidf_exe",
    type=click.Path(),
    help="Path to trnsidf.exe",
    default=os.path.join(
        settings.trnsys_default_folder, r"Building\trnsIDF\trnsidf.exe"
    ),
)
@click.option(
    "--template",
    type=click.Path(),
    default=settings.path_template_d18,
    help="Path to d18 template file",
)
@click.option(
    "--log_clear_names",
    is_flag=True,
    default=False,
    help='If mentioned (True), DO NOT print log of "clear_names" (equivalence between '
    "old and new names) in the console. Default (not mentioned) is False.",
)
@click.option(
    "--schedule_as_input",
    is_flag=True,
    default=True,
    help="If mentioned (False), writes schedules as SCHEDULES in BUI file. Be aware that "
    "this option might make crash TRNBuild. Default (not mentioned) is True, and "
    "writes the schedules as INPUTS. This option requires the user to link "
    "(in the TRNSYS Studio) the csv file containing the schedules with those INPUTS",
)
@click.option(
    "--ep_version",
    type=str,
    default=None,
    help="Specify the EnergyPlus version to use. Default = None",
)
@click.option(
    "--window",
    nargs=6,
    type=float,
    default=(2.2, 0.64, 0.8, 0.05, 0.15, 8.17),
    help="Specify window properties <u_value> <shgc> <t_vis> "
    "<tolerance> <fframe> <uframe>. Default = 2.2 0.64 0.8 0.05 0.15 8.17",
)
@click.option("--ordered", is_flag=True, help="sort idf object names")
@click.option("--nonum", is_flag=True, default=False, help="Do not renumber surfaces")
@click.option("--batchjob", "-N", is_flag=True, default=False, help="BatchJob Modus")
@click.option(
    "--geofloor",
    type=float,
    default=0.6,
    help="Generates GEOSURF values for distributing; direct solar "
    "radiation where `geo_floor` % is directed to the floor, "
    "the rest; to walls/windows. Default = 0.6",
)
@click.option(
    "--refarea",
    is_flag=True,
    default=False,
    help="Updates floor reference area of airnodes",
)
@click.option(
    "--volume", is_flag=True, default=False, help="Updates volume of airnodes"
)
@click.option(
    "--capacitance", is_flag=True, default=False, help="Updates capacitance of airnodes"
)
def convert(
    idf_file,
    weather_file,
    output_folder,
    return_idf,
    return_t3d,
    return_dck,
    window_lib,
    trnsidf_exe,
    template,
    log_clear_names,
    schedule_as_input,
    ep_version,
    window,
    ordered,
    nonum,
    batchjob,
    geofloor,
    refarea,
    volume,
    capacitance,
):
    """Convert regular IDF file (EnergyPlus) to TRNBuild file (TRNSYS) The
    output folder path defaults to the working directory. Equivalent to '.'

    """
    u_value, shgc, t_vis, tolerance, fframe, uframe = window
    window_kwds = {
        "u_value": u_value,
        "shgc": shgc,
        "t_vis": t_vis,
        "tolerance": tolerance,
        "fframe": fframe,
        "uframe": uframe,
    }
    paths = convert_idf_to_trnbuild(
        idf_file,
        weather_file,
        window_lib,
        return_idf,
        True,
        return_t3d,
        return_dck,
        output_folder,
        trnsidf_exe,
        template,
        log_clear_names=log_clear_names,
        schedule_as_input=schedule_as_input,
        ep_version=ep_version,
        **window_kwds,
        ordered=ordered,
        nonum=nonum,
        N=batchjob,
        geo_floor=geofloor,
        refarea=refarea,
        volume=volume,
        capacitance=capacitance,
    )
    # Print path of output files in console
    click.echo("Here are the paths to the different output files: ")

    for path in paths:
        if "MODIFIED" in path:
            click.echo("Path to the modified IDF file: {}".format(path))
        elif "b18" in path:
            click.echo("Path to the BUI file: {}".format(path))
        elif "dck" in path:
            click.echo("Path to the DCK file: {}".format(path))
        else:
            click.echo("Path to the T3D file: {}".format(path))


@timeit
@cli.command()
@click.argument("idf", nargs=-1, required=True)
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=True, writable=True),
    default="myumitemplate.json",
)
@click.option(
    "--weather",
    "-w",
    help="EPW weather file path",
    default=get_eplus_dirs(settings.ep_version)
    / "WeatherData"
    / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw",
    show_default=True,
)
@click.option(
    "-p",
    "--parallel",
    "cores",
    default=-1,
    help="Specify number of cores to run in parallel",
)
@click.option(
    "-z",
    "--all_zones",
    is_flag=True,
    default=False,
    help="Include all zones in the " "output template",
)
@click.option(
    "-v",
    "--version",
    "as_version",
    default=settings.ep_version,
    help="EnergyPlus version to upgrade to - e.g., '9-2-0'",
)
@click.pass_context
def reduce(ctx, idf, output, weather, cores, all_zones, as_version):
    """Convert EnergyPlus models to an Umi Template Library by using the model
    complexity reduction algorithm.

    IDF can be a file path or a directory. In case of a directory, all *.idf
    files will be matched in the directory and subdirectories (recursively). Mix &
    match is ok (see example below).
    OUTPUT is the output file
    name (or path) to write to. Optional.

    Example: % archetypal -v reduce "." "elsewhere/model1.idf" -w "weather.epw"

    """
    settings.use_cache = True

    output = Path(output)
    name = output.stem
    ext = output.ext if output.ext == ".json" else ".json"
    dir_ = output.dirname()

    file_paths = list(set_filepaths(idf))
    log(f"executing {len(file_paths)} file(s): {[file.stem for file in file_paths]}")
    weather = next(iter(set_filepaths([weather])))
    log(f"using the '{weather.basename()}' weather file\n")

    # Call UmiTemplateLibrary constructor with list of IDFs
    try:
        template = UmiTemplateLibrary.read_idf(
            file_paths,
            weather=weather,
            name=name,
            processors=cores,
            as_version=as_version,
            annual=True,
        )
    except Exception as e:
        if not ctx.obj.debug:
            pass
        else:
            raise e
    else:
        # Save json file
        final_path: Path = dir_ / name + ext
        template.to_json(path_or_buf=final_path, all_zones=all_zones)
        log("Successfully created template file at {}".format(final_path.abspath()))


@cli.command()
@click.argument("idf", nargs=-1, required=True)
@click.option(
    "-v",
    "--version",
    "to_version",
    default=settings.ep_version,
    help="EnergyPlus version to upgrade to - e.g., '9-2-0'",
)
@click.option(
    "-p",
    "--parallel",
    "cores",
    default=-1,
    help="Specify number of cores to run in parallel",
)
@click.option(
    "-y",
    "yes",
    is_flag=True,
    help="Suppress confirmation prompt, when overwriting files.",
)
@docstring_parameter(arversion=__version__, ep_version=ep_version)
def transition(idf, to_version, cores, yes):
    """Upgrade an IDF file to a newer version.

    IDF can be a file path or a directory. In case of a directory, all *.idf
    files will be found in the directory and subdirectories (recursively). Mix &
    match is ok (see example below).

    Example: % archetypal -v transition "." "elsewhere/model1.idf"

    archetypal will look in the current working directory (".") and find any
    *.idf files and also run the model located at "elsewhere/model1.idf".

    Note: The latest version archetypal v{arversion} can upgrade to is
    {ep_version}.

    """
    start_time = time.time()

    if not yes:
        overwrite = click.confirm("Would you like to overwrite the file(s)?")
    else:
        overwrite = False

    file_paths = set_filepaths(idf)
    rundict = {
        file: dict(
            idf_file=file, to_version=to_version, overwrite=overwrite, position=i + 1
        )
        for i, file in enumerate(file_paths)
    }
    parallel_process(
        rundict, idf_version_updater, processors=cores, show_progress=True, position=0
    )
    log(
        "Successfully transitioned files to version '{}' in {:,.2f} seconds".format(
            to_version, time.time() - start_time
        )
    )


def set_filepaths(idf):
    """Simplifies file-like paths, dir-like paths and Paths with wildcards. A
    list of unique paths is returned. For directories, Path.walkfiles("*.idfs")
    returns IDF files. For Paths with wildcards, glob(Path) is used to return
    whatever the pattern defines.

    Args:
        idf (list of (str or Path) or tuple of (str or Path)): A list of path-like
            objects. Can contain wildcards.

    Returns:
        set of Path: The set of a list of paths
    """
    if not isinstance(idf, (list, tuple)):
        raise ValueError("A list must be passed")
    idf = (Path(file_or_path).expand() for file_or_path in idf)  # make Paths
    file_paths = ()  # Placeholder for tuple of paths
    for file_or_path in idf:
        if file_or_path.isfile():  # if a file, concatenate into file_paths
            file_paths += tuple([file_or_path])
        elif file_or_path.isdir():  # if a directory, walkdir (recursive) and get *.idf
            file_paths += tuple(file_or_path.walkfiles("*.idf"))
        else:
            file_paths += tuple([Path(a).expand() for a in glob(file_or_path)])  # has
            # wildcard
    file_paths = set(file_paths)  # Only keep unique values
    return file_paths
