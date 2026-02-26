################################################################################
# Module: cli.py
# Description: Implements archetypal functions as Command Line Interfaces
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################
import os

import click
from path import Path

from archetypal import __version__, settings
from archetypal.umi_template import UmiTemplateLibrary
from archetypal.utils import config, log, parallel_process, timeit

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


class CliConfig:
    def __init__(self):
        self.data_folder = settings.data_folder
        self.logs_folder = settings.logs_folder
        self.imgs_folder = settings.imgs_folder
        self.cache_folder = settings.cache_folder
        self.cache_responses = settings.cache_responses
        self.log_file = settings.log_file
        self.log_console = settings.log_console
        self.log_level = settings.log_level
        self.log_name = settings.log_name
        self.log_filename = settings.log_filename


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
    help="where to save the simulation results",
    default=settings.cache_folder,
)
@click.option(
    "-c",
    "--cache-responses",
    is_flag=True,
    default=False,
    help="Use a local cache to save/retrieve API calls for the same requests.",
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
@click.option("--log-filename", help="name of the log file", default=settings.log_filename)
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
    cache_responses,
    log_file,
    log_console,
    log_level,
    log_name,
    log_filename,
    debug,
):
    """archetypal: Convert EnergyPlus models to UMI building templates.

    Visit archetypal.readthedocs.io for the online documentation.

    """
    cli_config.data_folder = data_folder
    cli_config.logs_folder = logs_folder
    cli_config.imgs_folder = imgs_folder
    cli_config.cache_folder = cache_folder
    cli_config.cache_responses = cache_responses
    cli_config.log_file = log_file
    cli_config.log_console = log_console
    cli_config.log_level = log_level
    cli_config.log_name = log_name
    cli_config.log_filename = log_filename
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
    required=True,
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
    help="Include all zones in the output template",
)
@click.pass_context
def reduce(ctx, idf, output, weather, cores, all_zones):
    """Convert EnergyPlus models to an Umi Template Library by using the model
    complexity reduction algorithm.

    IDF can be a file path or a directory. In case of a directory, all *.idf
    files will be matched in the directory and subdirectories (recursively). Mix &
    match is ok (see example below).
    OUTPUT is the output file
    name (or path) to write to. Optional.

    Example: % archetypal -csl reduce "." -w "weather.epw"

    """
    output = Path(output)
    name = output.stem
    ext = output.suffix if output.suffix == ".json" else ".json"
    dir_ = output.dirname()

    file_paths = list(set_filepaths(idf))
    file_list = "\n".join([f"{i}. " + str(file.name) for i, file in enumerate(file_paths)])
    log(
        f"executing {len(file_paths)} file(s):\n{file_list}",
    )
    weather, *_ = set_filepaths([weather])
    log(f"using the '{weather.basename()}' weather file\n")

    # Call UmiTemplateLibrary constructor with list of IDFs
    template = UmiTemplateLibrary.from_idf_files(
        file_paths,
        weather=weather,
        name=name,
        processors=cores,
        keep_all_zones=all_zones,
        annual=True,
    )
    # Save json file
    final_path: Path = dir_ / name + ext
    template.save(path_or_buf=final_path)
    log(
        f"Successfully created template file at {final_path.absolute()}",
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
        raise TypeError("A list must be passed")
    idf = tuple(Path(file_or_path).expand() for file_or_path in idf)  # make Paths
    file_paths = ()  # Placeholder for tuple of paths
    for file_or_path in idf:
        if file_or_path.is_file():  # if a file, concatenate into file_paths
            file_paths += (file_or_path,)
        elif file_or_path.is_dir():  # if a directory, walkdir (recursive) and get *.idf
            file_paths += tuple(file_or_path.walkfiles("*.idf"))
        else:
            # has wildcard
            excluded_dirs = [
                settings.cache_folder,
                settings.data_folder,
                settings.imgs_folder,
                settings.logs_folder,
            ]
            top = file_or_path.absolute().dirname()
            for root, _, _ in walkdirs(top, excluded_dirs):
                pattern = file_or_path.basename()
                file_paths += tuple(Path(root).files(pattern))

    file_paths = {f.relpath().expand() for f in file_paths}  # Only keep unique
    # values
    if file_paths:
        return file_paths
    else:
        raise FileNotFoundError


def walkdirs(top, excluded):
    for root, dirs, files in os.walk(top, topdown=True):
        yield root, dirs, files
        dirs[:] = [d for d in dirs if (Path(root) / d) not in excluded]
