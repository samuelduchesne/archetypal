################################################################################
# Module: cli.py
# Description: Implements archetypal functions as Command Line Interfaces
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################
import os
import time

import click
from path import Path

from archetypal import __version__, settings
from archetypal.idfclass import IDF
from archetypal.settings import ep_version
from archetypal.umi_template import UmiTemplateLibrary
from archetypal.utils import config, docstring_parameter, log, parallel_process, timeit

from .eplus_interface.exceptions import EnergyPlusVersionError
from .eplus_interface.version import EnergyPlusVersion, get_eplus_dirs

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
    help="Use a local cache to save/retrieve DataPortal API calls for the same "
    "requests.",
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
    cli_config.ep_version = ep_version
    cli_config.debug = debug
    # apply new config params
    config(**cli_config.__dict__)


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

    Example: % archetypal -csl reduce "." "elsewhere/model1.idf" -w "weather.epw"

    """
    output = Path(output)
    name = output.stem
    ext = output.ext if output.ext == ".json" else ".json"
    dir_ = output.dirname()

    file_paths = list(set_filepaths(idf))
    file_list = "\n".join(
        [f"{i}. " + str(file.name) for i, file in enumerate(file_paths)]
    )
    log(
        f"executing {len(file_paths)} file(s):\n{file_list}",
        verbose=True,
    )
    weather, *_ = set_filepaths([weather])
    log(f"using the '{weather.basename()}' weather file\n", verbose=True)

    # Call UmiTemplateLibrary constructor with list of IDFs
    template = UmiTemplateLibrary.from_idf_files(
        file_paths,
        weather=weather,
        name=name,
        processors=cores,
        keep_all_zones=all_zones,
        as_version=as_version,
        annual=True,
    )
    # Save json file
    final_path: Path = dir_ / name + ext
    template.save(path_or_buf=final_path)
    log(
        f"Successfully created template file at {final_path.abspath()}",
        verbose=True,
    )


def validate_energyplusversion(ctx, param, value):
    try:
        return EnergyPlusVersion(value)
    except EnergyPlusVersionError:
        raise click.BadParameter("invalid energyplus version")


def validate_paths(ctx, param, value):
    try:
        file_paths = set_filepaths(value)
        file_list = "\n".join(
            [f"{i}. " + str(file.name) for i, file in enumerate(file_paths)]
        )
        return file_paths, file_list
    except FileNotFoundError:
        raise click.BadParameter("no files were found.")


@cli.command()
@click.argument("idf", nargs=-1, required=True, callback=validate_paths)
@click.option(
    "-v",
    "--version",
    "to_version",
    default=settings.ep_version,
    help="EnergyPlus version to upgrade to - e.g., '9-2-0'",
    callback=validate_energyplusversion,
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

    Example: % archetypal -csl transition "." "elsewhere/model1.idf"

    archetypal will look in the current working directory (".") and find any
    *.idf files and also run the model located at "elsewhere/model1.idf".

    Note: The latest version archetypal v{arversion} can upgrade to is
    {ep_version}.

    """
    file_paths, file_list = idf
    log(
        f"executing {len(file_paths)} file(s):\n{file_list}",
        verbose=True,
    )
    if not yes:
        overwrite = click.confirm("Would you like to overwrite the file(s)?")
    else:
        overwrite = False
    start_time = time.time()

    to_version = to_version.dash
    rundict = {
        file: dict(
            idfname=file,
            as_version=to_version,
            check_required=False,
            check_length=False,
            overwrite=overwrite,
            prep_outputs=False,
        )
        for i, file in enumerate(file_paths)
    }
    results = parallel_process(
        rundict,
        IDF,
        processors=cores,
        show_progress=True,
        position=0,
        debug=False,
    )

    # Save results to file (overwriting if True)
    file_list = []
    for idf in results:
        if isinstance(idf, IDF):
            if overwrite:
                file_list.append(idf.original_idfname)
                idf.saveas(str(idf.original_idfname))
            else:
                full_path = (
                    idf.original_idfname.dirname() / idf.original_idfname.stem
                    + f"V{to_version}.idf"
                )
                file_list.append(full_path)
                idf.saveas(full_path)
    log(
        f"Successfully transitioned to version '{to_version}' in "
        f"{time.time() - start_time:,.2f} seconds for file(s):\n" + "\n".join(file_list)
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
    idf = tuple(Path(file_or_path).expand() for file_or_path in idf)  # make Paths
    file_paths = ()  # Placeholder for tuple of paths
    for file_or_path in idf:
        if file_or_path.isfile():  # if a file, concatenate into file_paths
            file_paths += tuple([file_or_path])
        elif file_or_path.isdir():  # if a directory, walkdir (recursive) and get *.idf
            file_paths += tuple(file_or_path.walkfiles("*.idf"))
        else:
            # has wildcard
            excluded_dirs = [
                settings.cache_folder,
                settings.data_folder,
                settings.imgs_folder,
                settings.logs_folder,
            ]
            top = file_or_path.abspath().dirname()
            for root, dirs, files in walkdirs(top, excluded_dirs):
                pattern = file_or_path.basename()
                file_paths += tuple(Path(root).files(pattern))

    file_paths = set([f.relpath().expand() for f in file_paths])  # Only keep unique
    # values
    if file_paths:
        return file_paths
    else:
        raise FileNotFoundError


def walkdirs(top, excluded):
    for root, dirs, files in os.walk(top, topdown=True):
        yield root, dirs, files
        dirs[:] = [d for d in dirs if (Path(root) / d) not in excluded]
