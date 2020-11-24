import hashlib
import logging as lg
import os
import platform
import subprocess
import sys
from collections import OrderedDict
from io import StringIO
from sqlite3.dbapi2 import OperationalError
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory

import eppy
import pandas as pd
from archetypal import log, close_logger, settings, __version__
from archetypal.eplus_interface.version import get_eplus_dirs, latest_energyplus_version
from deprecation import deprecated
from eppy.easyopen import getiddfile
from eppy.EPlusInterfaceFunctions import parse_idd
from path import Path
from tqdm import tqdm
from archetypal.eplus_interface.exceptions import (
    EnergyPlusProcessError,
    EnergyPlusVersionError,
)


def _run_exec(
    tmp,
    eplus_file,
    weather,
    output_directory,
    annual,
    design_day,
    idd,
    epmacro,
    expandobjects,
    readvars,
    output_prefix,
    output_suffix,
    version,
    verbose,
    ep_version,
    keep_data_err,
    include,
    custom_processes,
    **kwargs,
):
    """Wrapper around the EnergyPlus command line interface.

    Adapted from :func:`eppy.runner.runfunctions.run`.

    Args:
        tmp:
        eplus_file:
        weather:
        output_directory:
        annual:
        design_day:
        idd:
        epmacro:
        expandobjects:
        readvars:
        output_prefix:
        output_suffix:
        version:
        verbose:
        ep_version:
        keep_data_err:
        include:
    """

    args = locals().copy()
    kwargs = args.pop("kwargs")
    # get unneeded params out of args ready to pass the rest to energyplus.exe
    verbose = args.pop("verbose")
    eplus_file = args.pop("eplus_file")
    iddname = args.get("idd")
    tmp = args.pop("tmp")
    keep_data_err = args.pop("keep_data_err")
    output_directory = args.pop("tmp_dir")
    idd = args.pop("idd")
    include = args.pop("include")
    custom_processes = args.pop("custom_processes")
    try:
        idf_path = os.path.abspath(eplus_file.idfname)
    except AttributeError:
        idf_path = os.path.abspath(eplus_file)
    ep_version = args.pop("ep_version")
    # get version from IDF object or by parsing the IDF file for it
    if not ep_version:
        try:
            ep_version = "-".join(str(x) for x in eplus_file.idd_version[:3])
        except AttributeError:
            raise AttributeError(
                "The as_version must be set when passing an IDF path. \
                Alternatively, use IDF.run()"
            )

    eplus_exe_path, eplus_weather_path = eppy.runner.run_functions.install_paths(
        ep_version, iddname
    )
    if not Path(eplus_exe_path).exists():
        raise EnergyPlusVersionError(
            msg=f"No EnergyPlus Executable found for version {EnergyPlusVersion(ep_version)}"
        )
    if version:
        # just get EnergyPlus version number and return
        cmd = [eplus_exe_path, "--version"]
        subprocess.check_call(cmd)
        return

    # convert paths to absolute paths if required
    if os.path.isfile(args["weather"]):
        args["weather"] = os.path.abspath(args["weather"])
    else:
        args["weather"] = os.path.join(eplus_weather_path, args["weather"])
    # args['tmp_dir'] = tmp.abspath()

    with tmp.abspath() as tmp:
        # build a list of command line arguments
        cmd = [eplus_exe_path]
        for arg in args:
            if args[arg]:
                if isinstance(args[arg], bool):
                    args[arg] = ""
                cmd.extend(["--{}".format(arg.replace("_", "-"))])
                if args[arg] != "":
                    cmd.extend([args[arg]])
        cmd.extend([idf_path])
        position = kwargs.get("position", None)
        with tqdm(
            unit_scale=True,
            miniters=1,
            desc=f"simulate #{position}-{Path(idf_path).basename()}",
            position=position,
        ) as progress:
            with subprocess.Popen(
                cmd,
                shell=True,
                universal_newlines=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ) as process:
                _log_subprocess_output(
                    process.stdout,
                    name=eplus_file.basename(),
                    verbose=verbose,
                    progress=progress,
                )
                # We explicitly close stdout
                process.stdout.close()

                # wait for the return code
                return_code = process.wait()

                # if return code is not 0 this means our script errored out
                if return_code != 0:
                    error_filename = output_prefix + "out.err"
                    try:
                        with open(error_filename, "r") as stderr:
                            stderr_r = stderr.read()
                        if keep_data_err:
                            failed_dir = output_directory / "failed"
                            failed_dir.mkdir_p()
                            tmp.copytree(failed_dir / output_prefix)
                        raise EnergyPlusProcessError(
                            cmd=cmd, stderr=stderr_r, idf=eplus_file.abspath()
                        )
                    except FileNotFoundError:
                        raise CalledProcessError(
                            return_code, cmd=cmd, stderr=process.stderr
                        )


def _log_subprocess_output(pipe, name, verbose, progress):
    """
    Args:
        pipe:
        name:
        verbose:
        progress (tqdm): tqdm progress bar
    """
    logger = None
    for line in pipe:
        linetxt = line.decode("utf-8").strip("\n")
        if verbose:
            logger = log(
                linetxt,
                level=lg.DEBUG,
                name="eplus_run_" + name,
                filename="eplus_run_" + name,
                log_dir=os.getcwd(),
            )

        if linetxt != "" and progress is not None:
            progress.update()
    if logger:
        close_logger(logger)
    if pipe:
        sys.stdout.flush()


def hash_model(idfname, **kwargs):
    """Simple function to hash a file or IDF model and return it as a string. Will also
    hash the :func:`eppy.runner.run_functions.run()` arguments so that correct
    results are returned when different run arguments are used.

    Todo:
        Hashing should include the external files used an idf file. For example,
        if a model uses a csv file as an input and that file changes, the
        hashing will currently not pickup that change. This could result in
        loading old results without the user knowing.

    Args:
        idfname (str or IDF): path of the idf file or the IDF model itself.
        kwargs: keywargs to serialize in addition to the file content.

    Returns:
        str: The digest value as a string of hexadecimal digits
    """
    from .idf import IDF

    if kwargs:
        # Before we hash the kwargs, remove the ones that don't have an impact on
        # simulation results and so should not change the cache dirname.
        no_impact = ["keep_data", "keep_data_err", "return_idf", "return_files"]
        for argument in no_impact:
            _ = kwargs.pop(argument, None)

        # sorting keys for serialization of dictionary
        kwargs = OrderedDict(sorted(kwargs.items()))

    # create hasher
    hasher = hashlib.md5()
    if isinstance(idfname, StringIO):
        idfname.seek(0)
        buf = idfname.read().encode("utf-8")
    elif isinstance(idfname, IDF):
        buf = idfname.idfstr().encode("utf-8")
    else:
        with open(idfname, "rb") as afile:
            buf = afile.read()
    hasher.update(buf)
    hasher.update(kwargs.__str__().encode("utf-8"))  # Hashing the kwargs as well
    return hasher.hexdigest()


def get_report(
    eplus_file, output_directory=None, output_report="sql", output_prefix=None, **kwargs
):
    """Returns the specified report format (html or sql)

    Args:
        eplus_file (str): path of the idf file
        output_directory (str, optional): path to the output folder. Will
            default to the settings.cache_folder.
        output_report: 'htm' or 'sql'
        output_prefix (str): Prefix name given to results files.
        **kwargs: keyword arguments to pass to hasher.

    Returns:
        dict: a dict of DataFrames
    """
    if not output_directory:
        output_directory = settings.cache_folder
    # Hash the idf file with any kwargs used in the function
    if output_prefix is None:
        output_prefix = hash_model(eplus_file)
    if output_report is None:
        return None
    elif "htm" in output_report.lower():
        # Get the html report
        fullpath_filename = output_directory / output_prefix + "tbl.htm"
        if fullpath_filename.exists():
            return get_html_report(fullpath_filename)
        else:
            raise FileNotFoundError(
                'File "{}" does not exist'.format(fullpath_filename)
            )

    elif "sql" == output_report.lower():
        # Get the sql report
        fullpath_filename = output_directory / output_prefix + "out.sql"
        if fullpath_filename.exists():
            return get_sqlite_report(fullpath_filename)
        else:
            raise FileNotFoundError(
                'File "{}" does not exist'.format(fullpath_filename)
            )
    else:
        return None


def get_from_cache(kwargs):
    """Retrieve a EPlus Tabulated Summary run result from the cache

    Args:
        kwargs (dict): Args used to create the cache name.

    Returns:
        dict: dict of DataFrames
    """
    output_directory = Path(kwargs.get("tmp_dir"))
    output_report = kwargs.get("output_report")
    eplus_file = next(iter(output_directory.glob("*.idf")), None)
    if not eplus_file:
        return None
    if settings.use_cache:
        # determine the filename by hashing the eplus_file
        cache_filename_prefix = hash_model(eplus_file)

        if output_report is None:
            # No report is expected but we should still return the path if it exists.
            cached_run_dir = output_directory / cache_filename_prefix
            if cached_run_dir.exists():
                return cached_run_dir
            else:
                return None
        elif "htm" in output_report.lower():
            # Get the html report

            cache_fullpath_filename = (
                output_directory / cache_filename_prefix / cache_filename_prefix
                + "tbl.htm"
            )
            if cache_fullpath_filename.exists():
                return get_html_report(cache_fullpath_filename)

        elif "sql" == output_report.lower():
            # get the SQL report
            if not output_directory:
                output_directory = settings.cache_folder / cache_filename_prefix

            cache_fullpath_filename = (
                output_directory / cache_filename_prefix / cache_filename_prefix
                + "out.sql"
            )

            if cache_fullpath_filename.exists():
                # get reports from passed-in report names or from
                # settings.available_sqlite_tables if None are given
                return get_sqlite_report(
                    cache_fullpath_filename,
                    kwargs.get("report_tables", settings.available_sqlite_tables),
                )
        elif "sql_file" == output_report.lower():
            # get the SQL report
            if not output_directory:
                output_directory = settings.cache_folder / cache_filename_prefix

            cache_fullpath_filename = (
                output_directory / cache_filename_prefix / cache_filename_prefix
                + "out.sql"
            )
            if cache_fullpath_filename.exists():
                return cache_fullpath_filename


def get_html_report(report_fullpath):
    """Parses the html Summary Report for each tables into a dictionary of
    DataFrames

    Args:
        report_fullpath (str): full path to the report file

    Returns:
        dict: dict of {title : table <DataFrame>,...}
    """
    from eppy.results import readhtml  # the eppy module with functions to read the html

    with open(report_fullpath, "r", encoding="utf-8") as cache_file:
        filehandle = cache_file.read()  # get a file handle to the html file

        cached_tbl = readhtml.titletable(
            filehandle
        )  # get a file handle to the html file

        log('Retrieved response from cache file "{}"'.format(report_fullpath))
        return summary_reports_to_dataframes(cached_tbl)


def summary_reports_to_dataframes(reports_list):
    """Converts a list of [(title, table),...] to a dict of {title: table
    <DataFrame>}. Duplicate keys must have their own unique names in the output
    dict.

    Args:
        reports_list (list): a list of [(title, table),...]

    Returns:
        dict: a dict of {title: table <DataFrame>}
    """
    results_dict = {}
    for table in reports_list:
        key = str(table[0])
        if key in results_dict:  # Check if key is already exists in
            # dictionary and give it a new name
            key = key + "_"
        df = pd.DataFrame(table[1])
        df = df.rename(columns=df.iloc[0]).drop(df.index[0])
        results_dict[key] = df
    return results_dict


def get_sqlite_report(report_file, report_tables=None):
    """Connects to the EnergyPlus SQL output file and retreives all tables

    Args:
        report_file (str): path of report file
        report_tables (list, optional): list of report table names to retreive.
            Defaults to settings.available_sqlite_tables

    Returns:
        dict: dict of DataFrames
    """
    # set list of report tables
    if not report_tables:
        report_tables = settings.available_sqlite_tables

    # if file exists, parse it with pandas' read_sql_query
    if os.path.isfile(report_file):
        import sqlite3

        import numpy as np

        # create database connection with sqlite3
        with sqlite3.connect(report_file) as conn:
            # empty dict to hold all DataFrames
            all_tables = {}
            # Iterate over all tables in the report_tables list
            for table in report_tables:
                try:
                    # Try regular str read, could fail if wrong encoding
                    conn.text_factory = str
                    df = pd.read_sql_query(
                        "select * from {};".format(table),
                        conn,
                        index_col=report_tables[table]["PrimaryKey"],
                        parse_dates=report_tables[table]["ParseDates"],
                        coerce_float=True,
                    )
                    all_tables[table] = df
                except OperationalError:
                    # Wring encoding found, the load bytes and ecode object
                    # columns only
                    conn.text_factory = bytes
                    df = pd.read_sql_query(
                        "select * from {};".format(table),
                        conn,
                        index_col=report_tables[table]["PrimaryKey"],
                        parse_dates=report_tables[table]["ParseDates"],
                        coerce_float=True,
                    )
                    str_df = df.select_dtypes([np.object])
                    str_df = str_df.stack().str.decode("8859").unstack()
                    for col in str_df:
                        df[col] = str_df[col]
                    all_tables[table] = df
            log(
                "SQL query parsed {} tables as DataFrames from {}".format(
                    len(all_tables), report_file
                )
            )
            return all_tables


def idf_version_updater(
    idf_file, to_version=None, out_dir=None, simulname=None, overwrite=True, **kwargs
):
    """EnergyPlus idf version updater using local transition program.

    Update the EnergyPlus simulation file (.idf) to the latest available
    EnergyPlus version installed on this machine. Optionally specify a version
    (eg.: "9-2-0") to aim for a specific version. The output will be the path of
    the updated file. The run is multiprocessing_safe.

    Hint:
        If attempting to upgrade an earlier version of EnergyPlus ( pre-v7.2.0),
        specific binaries need to be downloaded and copied to the
        EnergyPlus*/PreProcess/IDFVersionUpdater folder. More info at
        `Converting older version files
        <http://energyplus.helpserve.com/Knowledgebase/List/Index/46
        /converting-older-version-files>`_ .

    Args:
        overwrite (bool):
        idf_file (Path): path of idf file
        to_version (str, optional): EnergyPlus version in the form "X-X-X".
        out_dir (Path): path of the output_dir
        simulname (str or None, optional): this name will be used for temp dir
            id and saved outputs. If not provided, uuid.uuid1() is used. Be
            careful to avoid naming collision : the run will always be done in
            separated folders, but the output files can overwrite each other if
            the simulname is the same. (default: None)

    Raises:
        EnergyPlusProcessError: If version updater fails.
        EnergyPlusVersionError:
        CalledProcessError:

    Returns:
        Path: The path of the new transitioned idf file.
    """
    idf_file = Path(idf_file)
    if not out_dir:
        # if no directory is provided, use directory of file
        out_dir = idf_file.dirname()
    if not out_dir.isdir() and out_dir != "":
        # check if dir exists
        out_dir.makedirs_p()

    to_version, versionid = _check_version(idf_file, to_version, out_dir)

    if versionid == to_version:
        # check the file version, if it corresponds to the latest version found on
        # the machine, means its already upgraded to the correct version.
        # if file version and to_version are the same, we don't need to
        # perform transition.
        log(
            'file {} already upgraded to latest version "{}"'.format(
                idf_file, versionid
            )
        )
        return idf_file
    else:
        # execute transitions
        with TemporaryDirectory(
            prefix="transition_run_", suffix=None, dir=out_dir
        ) as tmp:
            # Move to temporary transition_run folder
            log(f"temporary dir ({Path(tmp).expand()}) created", lg.DEBUG)
            idf_file = Path(idf_file.copy(tmp)).abspath()  # copy and return abspath
            try:
                _execute_transitions(idf_file, to_version, versionid, **kwargs)
            except (CalledProcessError, EnergyPlusProcessError) as e:
                raise e

            # retrieve transitioned file
            for f in Path(tmp).files("*.idfnew"):
                if overwrite:
                    file = f.copy(out_dir / idf_file.basename())
                else:
                    file = f.copy(out_dir)
        return file


def _check_version(idf_file, to_version, out_dir):
    versionid = get_idf_version(idf_file, doted=False)[0:5]
    doted_version = get_idf_version(idf_file, doted=True)
    iddfile = getiddfile(doted_version)
    if os.path.exists(iddfile):
        # if a E+ exists, means there is an E+ install that can be used
        if versionid == to_version:
            # if version of idf file is equal to intended version, copy file from
            # temp transition folder into cache folder and return path
            return to_version, versionid
    # might be an old version of E+
    elif tuple(map(int, doted_version.split("."))) < (8, 0):
        # the version is an old E+ version (< 8.0)
        iddfile = getoldiddfile(doted_version)
        if versionid == to_version:
            # if version of idf file is equal to intended version, copy file from
            # temp transition folder into cache folder and return path
            return idf_file.copy(out_dir / idf_file.basename())
    # use to_version
    if to_version is None:
        # What is the latest E+ installed version
        to_version = latest_energyplus_version()
    if tuple(versionid.split("-")) > tuple(to_version.split("-")):
        raise EnergyPlusVersionError(idf_file, versionid, to_version)
    return to_version, versionid


@deprecated(
    deprecated_in="1.3.5",
    removed_in="1.4",
    current_version=__version__,
    details="Use :func:`IDF._execute_transitions` instead",
)
def _execute_transitions(idf_file, to_version, versionid, **kwargs):
    """build a list of command line arguments"""
    vupdater_path = (
        get_eplus_dirs(settings.ep_version) / "PreProcess" / "IDFVersionUpdater"
    )
    exe = ".exe" if platform.system() == "Windows" else ""
    trans_exec = {
        "1-0-0": vupdater_path / "Transition-V1-0-0-to-V1-0-1" + exe,
        "1-0-1": vupdater_path / "Transition-V1-0-1-to-V1-0-2" + exe,
        "1-0-2": vupdater_path / "Transition-V1-0-2-to-V1-0-3" + exe,
        "1-0-3": vupdater_path / "Transition-V1-0-3-to-V1-1-0" + exe,
        "1-1-0": vupdater_path / "Transition-V1-1-0-to-V1-1-1" + exe,
        "1-1-1": vupdater_path / "Transition-V1-1-1-to-V1-2-0" + exe,
        "1-2-0": vupdater_path / "Transition-V1-2-0-to-V1-2-1" + exe,
        "1-2-1": vupdater_path / "Transition-V1-2-1-to-V1-2-2" + exe,
        "1-2-2": vupdater_path / "Transition-V1-2-2-to-V1-2-3" + exe,
        "1-2-3": vupdater_path / "Transition-V1-2-3-to-V1-3-0" + exe,
        "1-3-0": vupdater_path / "Transition-V1-3-0-to-V1-4-0" + exe,
        "1-4-0": vupdater_path / "Transition-V1-4-0-to-V2-0-0" + exe,
        "2-0-0": vupdater_path / "Transition-V2-0-0-to-V2-1-0" + exe,
        "2-1-0": vupdater_path / "Transition-V2-1-0-to-V2-2-0" + exe,
        "2-2-0": vupdater_path / "Transition-V2-2-0-to-V3-0-0" + exe,
        "3-0-0": vupdater_path / "Transition-V3-0-0-to-V3-1-0" + exe,
        "3-1-0": vupdater_path / "Transition-V3-1-0-to-V4-0-0" + exe,
        "4-0-0": vupdater_path / "Transition-V4-0-0-to-V5-0-0" + exe,
        "5-0-0": vupdater_path / "Transition-V5-0-0-to-V6-0-0" + exe,
        "6-0-0": vupdater_path / "Transition-V6-0-0-to-V7-0-0" + exe,
        "7-0-0": vupdater_path / "Transition-V7-0-0-to-V7-1-0" + exe,
        "7-1-0": vupdater_path / "Transition-V7-1-0-to-V7-2-0" + exe,
        "7-2-0": vupdater_path / "Transition-V7-2-0-to-V8-0-0" + exe,
        "8-0-0": vupdater_path / "Transition-V8-0-0-to-V8-1-0" + exe,
        "8-1-0": vupdater_path / "Transition-V8-1-0-to-V8-2-0" + exe,
        "8-2-0": vupdater_path / "Transition-V8-2-0-to-V8-3-0" + exe,
        "8-3-0": vupdater_path / "Transition-V8-3-0-to-V8-4-0" + exe,
        "8-4-0": vupdater_path / "Transition-V8-4-0-to-V8-5-0" + exe,
        "8-5-0": vupdater_path / "Transition-V8-5-0-to-V8-6-0" + exe,
        "8-6-0": vupdater_path / "Transition-V8-6-0-to-V8-7-0" + exe,
        "8-7-0": vupdater_path / "Transition-V8-7-0-to-V8-8-0" + exe,
        "8-8-0": vupdater_path / "Transition-V8-8-0-to-V8-9-0" + exe,
        "8-9-0": vupdater_path / "Transition-V8-9-0-to-V9-0-0" + exe,
        "9-0-0": vupdater_path / "Transition-V9-0-0-to-V9-1-0" + exe,
        "9-1-0": vupdater_path / "Transition-V9-1-0-to-V9-2-0" + exe,
    }

    transitions = [
        key
        for key in trans_exec
        if tuple(map(int, key.split("-"))) < tuple(map(int, to_version.split("-")))
        and tuple(map(int, key.split("-"))) >= tuple(map(int, versionid.split("-")))
    ]
    position = kwargs.get("position", None)
    for trans in tqdm(transitions, position=position, desc=f"file #{position}"):
        if not trans_exec[trans].exists():
            raise EnergyPlusProcessError(
                cmd=trans_exec[trans],
                stderr="The specified EnergyPlus version (v{}) does not have"
                " the required transition program '{}' in the "
                "PreProcess folder. See the documentation "
                "(archetypal.readthedocs.io/troubleshooting.html#missing"
                "-transition-programs) "
                "to solve this issue".format(to_version, trans_exec[trans]),
                idf=idf_file.abspath(),
            )
        else:
            cmd = [trans_exec[trans], idf_file]
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=vupdater_path,
                )
                process_output, error_output = process.communicate()
                log(process_output.decode("utf-8"), lg.DEBUG)
            except CalledProcessError as exception:
                log(
                    "{} failed with error\n".format(
                        idf_version_updater.__name__, str(exception)
                    ),
                    lg.ERROR,
                )


def get_idf_version(file, doted=True):
    """Get idf version quickly by reading first few lines of idf file containing
    the 'VERSION' identifier

    Args:
        file (str or StringIO): Absolute or relative Path to the idf file
        doted (bool, optional): Wheter or not to return the version number

    Returns:
        str: the version id
    """
    if isinstance(file, StringIO):
        file.seek(0)
        txt = file.read()
    else:
        with open(os.path.abspath(file), "r", encoding="latin-1") as fhandle:
            txt = fhandle.read()
    try:
        ntxt = parse_idd.nocomment(txt, "!")
        blocks = ntxt.split(";")
        blocks = [block.strip() for block in blocks]
        bblocks = [block.split(",") for block in blocks]
        bblocks1 = [[item.strip() for item in block] for block in bblocks]
        ver_blocks = [block for block in bblocks1 if block[0].upper() == "VERSION"]
        ver_block = ver_blocks[0]
        if doted:
            versionid = ver_block[1]
        else:
            versionid = ver_block[1].replace(".", "-") + "-0"
    except Exception as e:
        log('Version id for file "{}" cannot be found'.format(file))
        log("{}".format(e))
        raise
    else:
        return versionid


def getoldiddfile(versionid):
    """find the IDD file of the E+ installation E+ version 7 and earlier have
    the idd in /EnergyPlus-7-2-0/bin/Energy+.idd

    Args:
        versionid:
    """
    vlist = versionid.split(".")
    if len(vlist) == 1:
        vlist = vlist + ["0", "0"]
    elif len(vlist) == 2:
        vlist = vlist + ["0"]
    ver_str = "-".join(vlist)
    eplus_exe, _ = eppy.runner.run_functions.install_paths(ver_str)
    eplusfolder = os.path.dirname(eplus_exe)
    iddfile = "{}/bin/Energy+.idd".format(eplusfolder)
    return iddfile
