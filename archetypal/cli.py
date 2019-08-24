################################################################################
# Module: cli.py
# Description: Implements archetypal functions as Command Line Interfaces
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################
import os
from collections import defaultdict

import archetypal
import click
from archetypal import settings, cd, load_idf

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


class Config(object):
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


pass_config = click.make_pass_decorator(Config, ensure=True)


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
    "--use-cache",
    is_flag=True,
    help="Use a local cache to save/retrieve many of "
    "archetypal outputs such as EnergyPlus simulation results",
    default=settings.use_cache,
)
@click.option(
    "--log-file",
    is_flag=True,
    help="save log output to a log file in logs_folder",
    default=settings.log_file,
)
@click.option(
    "--log-console",
    "--verbose",
    "-v",
    is_flag=True,
    default=settings.log_console,
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
@pass_config
def cli(
    config,
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
):
    """archetypal: Retrieve, construct, simulate, convert and analyse building
    simulation templates

    Visit archetypal.readthedocs.io for the online documentation

    Args:
        config:
        data_folder:
        logs_folder:
        imgs_folder:
        cache_folder:
        use_cache:
        log_file:
        log_console:
        log_level:
        log_name:
        log_filename:
        trnsys_default_folder:
    """
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
@click.argument("idf-file", type=click.Path(exists=True))
@click.argument(
    "output-folder", type=click.Path(exists=True), required=False, default="."
)
@click.option(
    "--return-idf",
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
    "--window-lib",
    type=click.Path(),
    default=None,
    help="Path of the window library (from Berkeley Lab)",
)
@click.option(
    "--trnsidf-exe",
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
    "--log-clear-names",
    is_flag=True,
    default=False,
    help='Do not print log of "clear_names" (equivalence between '
    "old and new names) in the console",
)
@click.option(
    "--window",
    nargs=4,
    type=float,
    default=(2.2, 0.64, 0.8, 0.05),
    help="Specify window properties <u_value> <shgc> <t_vis> "
    "<tolerance>. Default = 2.2 0.64 0.8 0.05",
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
    help="Upadtes floor reference area of airnodes",
)
@click.option(
    "--volume", is_flag=True, default=False, help="Upadtes volume of airnodes"
)
@click.option(
    "--capacitance", is_flag=True, default=False, help="Upadtes capacitance of airnodes"
)
def convert(
    idf_file,
    window_lib,
    return_idf,
    return_t3d,
    return_dck,
    output_folder,
    trnsidf_exe,
    template,
    log_clear_names,
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

    Args:
        idf_file:
        window_lib:
        return_idf:
        return_t3d:
        return_dck:
        output_folder:
        trnsidf_exe:
        template:
        log_clear_names:
        window:
        ordered:
        nonum:
        batchjob:
        geofloor:
        refarea:
        volume:
        capacitance:
    """
    u_value, shgc, t_vis, tolerance = window
    window_kwds = {
        "u_value": u_value,
        "shgc": shgc,
        "t_vis": t_vis,
        "tolerance": tolerance,
    }
    with cd(output_folder):
        paths = archetypal.convert_idf_to_trnbuild(
            idf_file,
            window_lib,
            return_idf,
            True,
            return_t3d,
            return_dck,
            output_folder,
            trnsidf_exe,
            template,
            log_clear_names=log_clear_names,
            **window_kwds,
            ordered=ordered,
            nonum=nonum,
            N=batchjob,
            geo_floor=geofloor,
            refarea=refarea,
            volume=volume,
            capacitance=capacitance
        )
    # Print path of output files in console
    if paths:
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


@cli.command()
@click.argument("idf", nargs=-1)
@click.option(
    "--name",
    "-n",
    type=click.STRING,
    default="umitemplate",
    help="The name of the output json file",
)
@click.option(
    "--ep-version",
    type=click.STRING,
    help="specify the version of EnergyPlus to use, eg.: '8-9-0'",
    default="8-9-0",
)
@click.option(
    "--weather",
    "-w",
    type=click.Path(exists=True),
    help="path to the EPW weather file",
    default=archetypal.get_eplus_dire()
    / "WeatherData"
    / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw",
)
@click.option(
    "--parallel/--no-parallel",
    "-p/-np",
    is_flag=True,
    default=True,
    help="process each idf file on different cores",
)
def reduce(idf, name, ep_version, weather, parallel):
    """Perform the model reduction and translate to an UMI template file.

    Args:
        idf:
        name:
        weather:
        parallel:
    """
    if parallel:
        # if parallel is True, run eplus in parallel
        rundict = {
            file: dict(
                eplus_file=file,
                weather_file=weather,
                annual=True,
                prep_outputs=True,
                expandobjects=True,
                verbose="v",
                output_report="sql",
                return_idf=False,
                ep_version=ep_version,
            )
            for file in idf
        }
        res = archetypal.parallel_process(rundict, archetypal.run_eplus)
        loaded_idf = {}
        for key, sql in res.items():
            loaded_idf[key] = {}
            loaded_idf[key][0] = sql
            loaded_idf[key][1] = load_idf(key)
        res = loaded_idf
    else:
        # else, run sequentially
        res = defaultdict(dict)
        for fn in idf:
            res[fn][0], res[fn][1] = archetypal.run_eplus(
                fn,
                weather,
                ep_version=ep_version,
                output_report="sql",
                prep_outputs=True,
                annual=True,
                design_day=False,
                verbose="v",
                return_idf=True,
            )
    from archetypal import BuildingTemplate

    bts = []
    for fn in res.values():
        sql = next(
            iter([value for key, value in fn.items() if isinstance(value, dict)])
        )
        idf = next(
            iter(
                [
                    value
                    for key, value in fn.items()
                    if isinstance(value, archetypal.IDF)
                ]
            )
        )
        bts.append(BuildingTemplate.from_idf(idf, sql=sql, DataSource=idf.name))

    template = archetypal.UmiTemplate(name=name, BuildingTemplates=bts)
    print(template.to_json())
