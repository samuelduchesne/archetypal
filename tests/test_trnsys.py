import io
import os

import pytest

import archetypal as ar

import pandas as pd

from path import Path

from copy import deepcopy

from archetypal import (
    convert_idf_to_trnbuild,
    parallel_process,
    trnbuild_idf,
    copy_file,
    load_idf,
    settings,
    choose_window,
    run_eplus,
    ReportData,
    get_eplus_dirs,
)

# Function round to hundreds
from archetypal.trnsys import (
    _assert_files,
    load_idf_file_and_clean_names,
    clear_name_idf_objects,
    get_idf_objects,
    _get_constr_list,
    _order_objects,
    _get_schedules,
    _yearlySched_to_csv,
    _remove_low_conductivity,
    _write_version,
    _write_building,
    _add_change_adj_surf,
    _write_location_geomrules,
    _is_coordSys_world,
    _change_relative_coords,
    _get_ground_vertex,
    _write_zone_buildingSurf_fenestrationSurf,
    _write_constructions,
    _write_constructions_end,
    _write_materials,
    _write_gains,
    _write_conditioning,
    _write_schedules,
    _write_window,
    _write_winPool,
    _save_t3d,
    _relative_to_absolute,
    infilt_to_b18,
    gains_to_b18,
    conditioning_to_b18,
    adds_sch_ground,
    adds_sch_setpoint,
)
from tests.conftest import get_platform


@pytest.fixture(
    scope="class", params=["tests/input_data/trnsys/simple_2_zone_sched.idf",],
)
def converttesteasy(request):
    file = request.param
    window_file = "W74-lib.dat"
    template_dir = os.path.join("archetypal", "ressources")
    window_filepath = os.path.join(template_dir, window_file)
    template_d18 = "tests/input_data/trnsys/NewFileTemplate.d18"
    trnsidf_exe = "docker/trnsidf/trnsidf.exe"  # 'docker/trnsidf/trnsidf.exe'

    # prepare args (key=value). Key is a unique id for the runs (here the
    # file basename is used). Value is a dict of the function arguments
    kwargs_dict = {
        "u_value": 2.5,
        "shgc": 0.6,
        "t_vis": 0.78,
        "tolerance": 0.05,
        "ordered": True,
    }
    idf = load_idf(file)

    weather_file = os.path.join(
        "tests", "input_data", "CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    )

    yield idf, file, weather_file, window_filepath, trnsidf_exe, template_d18, kwargs_dict

    del idf


class TestConvertEasy:

    """Tests convert_idf_to_trnbuild() 1 file"""

    def test_get_save_write_schedules_as_sched(self, config, converttesteasy):
        output_folder = None
        (
            idf,
            idf_file,
            weather_file,
            window_lib,
            trnsidf_exe,
            template,
            _,
        ) = converttesteasy
        lines = io.TextIOWrapper(io.BytesIO(settings.template_BUI)).readlines()
        try:
            (
                idf_file,
                weather_file,
                window_lib,
                output_folder,
                trnsidf_exe,
                template,
            ) = _assert_files(
                idf_file, weather_file, window_lib, output_folder, trnsidf_exe, template
            )
        except:
            output_folder = os.path.relpath(settings.data_folder)
            print("Could not assert all paths exist - OK for this test")
        schedule_names, schedules = _get_schedules(idf)
        _yearlySched_to_csv(idf_file, output_folder, schedule_names, schedules)
        schedule_as_input = False
        schedules_not_written = _write_schedules(
            lines, schedule_names, schedules, schedule_as_input, idf_file
        )

    def test_write_version_and_building(self, config, converttesteasy):
        (
            idf,
            idf_file,
            weather_file,
            window_lib,
            trnsidf_exe,
            template,
            _,
        ) = converttesteasy
        (
            buildingSurfs,
            buildings,
            constructions,
            equipments,
            fenestrationSurfs,
            globGeomRules,
            lights,
            locations,
            materialAirGap,
            materialNoMass,
            materials,
            peoples,
            versions,
            zones,
            zonelists,
        ) = get_idf_objects(idf)
        lines = io.TextIOWrapper(io.BytesIO(settings.template_BUI)).readlines()
        _write_version(lines, versions)
        _write_building(buildings, lines)

    def test_write_material(self, config, converttesteasy):
        (
            idf,
            idf_file,
            weather_file,
            window_lib,
            trnsidf_exe,
            template,
            _,
        ) = converttesteasy

        # Read IDF_T3D template and write lines in variable
        lines = io.TextIOWrapper(io.BytesIO(settings.template_BUI)).readlines()

        # Get objects from IDF file
        (
            buildingSurfs,
            buildings,
            constructions,
            equipments,
            fenestrationSurfs,
            globGeomRules,
            lights,
            locations,
            materialAirGap,
            materialNoMass,
            materials,
            peoples,
            versions,
            zones,
            zonelists,
        ) = get_idf_objects(idf)

        # Write LAYER from IDF to lines (T3D)
        _write_materials(lines, materialAirGap, materialNoMass, materials)

    def test_relative_to_absolute(self, config, converttesteasy):
        output_folder = None
        (
            idf,
            idf_file,
            weather_file,
            window_lib,
            trnsidf_exe,
            template,
            _,
        ) = converttesteasy
        try:
            (
                idf_file,
                weather_file,
                window_lib,
                output_folder,
                trnsidf_exe,
                template,
            ) = _assert_files(
                idf_file, weather_file, window_lib, output_folder, trnsidf_exe, template
            )
        except:
            output_folder = os.path.relpath(settings.data_folder)
            print("Could not assert all paths exist - OK for this test")

        # Check if cache exists
        log_clear_names = False
        idf = load_idf(idf_file)

        # Clean names of idf objects (e.g. 'MATERIAL')
        idf_2 = deepcopy(idf)
        clear_name_idf_objects(idf_2, log_clear_names)

        # Get objects from IDF file
        (
            buildingSurfs,
            buildings,
            constructions,
            equipments,
            fenestrationSurfs,
            globGeomRules,
            lights,
            locations,
            materialAirGap,
            materialNoMass,
            materials,
            peoples,
            versions,
            zones,
            zonelists,
        ) = get_idf_objects(idf_2)

        _relative_to_absolute(buildingSurfs[0], 1, 2, 3)

    def test_save_t3d(self, config, converttesteasy):
        output_folder = None
        (
            idf,
            idf_file,
            weather_file,
            window_lib,
            trnsidf_exe,
            template,
            _,
        ) = converttesteasy
        try:
            (
                idf_file,
                weather_file,
                window_lib,
                output_folder,
                trnsidf_exe,
                template,
            ) = _assert_files(
                idf_file, weather_file, window_lib, output_folder, trnsidf_exe, template
            )
        except:
            output_folder = os.path.relpath(settings.data_folder)
            print("Could not assert all paths exist - OK for this test")

        # Read IDF_T3D template and write lines in variable
        lines = io.TextIOWrapper(io.BytesIO(settings.template_BUI)).readlines()

        # Save T3D file at output_folder
        output_folder, t3d_path = _save_t3d(idf_file, lines, output_folder)

    def test_write_to_b18(self, config, converttesteasy):
        output_folder = None
        (
            idf,
            idf_file,
            weather_file,
            window_lib,
            trnsidf_exe,
            template,
            kwargs,
        ) = converttesteasy
        try:
            (
                idf_file,
                weather_file,
                window_lib,
                output_folder,
                trnsidf_exe,
                template,
            ) = _assert_files(
                idf_file, weather_file, window_lib, output_folder, trnsidf_exe, template
            )
        except:
            output_folder = os.path.relpath(settings.data_folder)
            print("Could not assert all paths exist - OK for this test")

        # Run EnergyPlus Simulation
        res = run_eplus(
            idf_file,
            weather_file,
            output_directory=None,
            ep_version=None,
            output_report="htm",
            prep_outputs=True,
            design_day=True,
        )

        # Check if cache exists
        log_clear_names = False
        idf = load_idf(idf_file)

        # Clean names of idf objects (e.g. 'MATERIAL')
        idf_2 = deepcopy(idf)
        clear_name_idf_objects(idf_2, log_clear_names)

        # Get old:new names equivalence
        old_new_names = pd.read_csv(
            os.path.join(
                settings.data_folder,
                Path(idf_file).basename().stripext() + "_old_new_names_equivalence.csv",
            )
        ).to_dict()

        # Get objects from IDF file
        (
            buildingSurfs,
            buildings,
            constructions,
            equipments,
            fenestrationSurfs,
            globGeomRules,
            lights,
            locations,
            materialAirGap,
            materialNoMass,
            materials,
            peoples,
            versions,
            zones,
            zonelists,
        ) = get_idf_objects(idf_2)

        b18_path = "tests/input_data/trnsys/T3D_simple_2_zone.b18"

        schedules_not_written = []

        heat_name = {}
        for i in range(0, len(res["Zone Sensible Heating"])):
            key = res["Zone Sensible Heating"].iloc[i, 0]
            name = "HEAT_z" + str(res["Zone Sensible Heating"].iloc[i].name)
            heat_name[key] = name

        cool_name = {}
        for i in range(0, len(res["Zone Sensible Cooling"])):
            key = res["Zone Sensible Cooling"].iloc[i, 0]
            name = "HEAT_z" + str(res["Zone Sensible Cooling"].iloc[i].name)
            cool_name[key] = name

        with open(b18_path) as b18_file:
            b18_lines = b18_file.readlines()

        zones = zones[0:2]
        peoples = peoples[0:2]
        equipments = equipments[0:2]
        lights = lights[0:2]

        infilt_to_b18(b18_lines, zones, res)

        # Tests both cases
        for cond in [True, False]:
            schedule_as_input = cond
            gains_to_b18(
                b18_lines,
                zones,
                zonelists,
                peoples,
                lights,
                equipments,
                schedules_not_written,
                res,
                old_new_names,
                schedule_as_input,
            )

        conditioning_to_b18(b18_lines, heat_name, cool_name, zones, old_new_names)

    def test_load_idf_file_and_clean_names(self, config, converttesteasy):
        (
            idf,
            idf_file,
            weather_file,
            window_lib,
            trnsidf_exe,
            template,
            _,
        ) = converttesteasy
        log_clear_names = False
        idf_2 = load_idf_file_and_clean_names(idf_file, log_clear_names)

        # Makes sure material names are unique and are 8 characters long
        name = None
        unique = False
        length = False
        for liste in idf_2.idfobjects["MATERIAL"].list2:
            if liste[1] != name:
                unique = True
                name = liste[1]
            else:
                unique = False
            if len(liste[1]) == 8:
                length = True
            else:
                length = False

        assert type(idf_2) == ar.idfclass.IDF
        assert unique
        assert length


@pytest.fixture(
    scope="class",
    params=[
        "RefBldgWarehouseNew2004_Chicago.idf",
        "ASHRAE9012016_Warehouse_Denver.idf",
        "ASHRAE9012016_ApartmentMidRise_Denver.idf",
        "5ZoneGeometryTransform.idf",
    ],
)
def converttest(request):
    file = get_eplus_dirs(settings.ep_version) / "ExampleFiles" / request.param
    # file = request.param
    window_file = "W74-lib.dat"
    template_dir = os.path.join("archetypal", "ressources")
    window_filepath = os.path.join(template_dir, window_file)
    template_d18 = "tests/input_data/trnsys/NewFileTemplate.d18"
    trnsidf_exe = "docker/trnsidf/trnsidf.exe"  # 'docker/trnsidf/trnsidf.exe'

    # prepare args (key=value). Key is a unique id for the runs (here the
    # file basename is used). Value is a dict of the function arguments
    kwargs_dict = {
        "u_value": 2.5,
        "shgc": 0.6,
        "t_vis": 0.78,
        "tolerance": 0.05,
        "ordered": True,
    }
    idf = load_idf(file)

    weather_file = os.path.join(
        "tests", "input_data", "CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    )

    yield idf, file, weather_file, window_filepath, trnsidf_exe, template_d18, kwargs_dict

    del idf


class TestConvert:

    """Tests convert_idf_to_trnbuild() with several files"""

    def test_get_save_write_schedules_as_input(self, config, converttest):
        output_folder = None
        idf, idf_file, weather_file, window_lib, trnsidf_exe, template, _ = converttest
        lines = io.TextIOWrapper(io.BytesIO(settings.template_BUI)).readlines()
        try:
            (
                idf_file,
                weather_file,
                window_lib,
                output_folder,
                trnsidf_exe,
                template,
            ) = _assert_files(
                idf_file, weather_file, window_lib, output_folder, trnsidf_exe, template
            )
        except:
            output_folder = os.path.relpath(settings.data_folder)
            print("Could not assert all paths exist - OK for this test")
        schedule_names, schedules = _get_schedules(idf)
        _yearlySched_to_csv(idf_file, output_folder, schedule_names, schedules)
        schedule_as_input = True
        schedules_not_written = _write_schedules(
            lines, schedule_names, schedules, schedule_as_input, idf_file
        )

    def test_write_idf_objects(self, config, converttest):
        (
            idf,
            idf_file,
            weather_file,
            window_lib,
            trnsidf_exe,
            template,
            kwargs,
        ) = converttest

        # Read IDF_T3D template and write lines in variable
        lines = io.TextIOWrapper(io.BytesIO(settings.template_BUI)).readlines()

        # Get objects from IDF file
        (
            buildingSurfs,
            buildings,
            constructions,
            equipments,
            fenestrationSurfs,
            globGeomRules,
            lights,
            locations,
            materialAirGap,
            materialNoMass,
            materials,
            peoples,
            versions,
            zones,
            zonelists,
        ) = get_idf_objects(idf)

        # Get all construction EXCEPT fenestration ones
        constr_list = _get_constr_list(buildingSurfs)

        # If ordered=True, ordering idf objects
        ordered = True
        (
            buildingSurfs,
            buildings,
            constr_list,
            constructions,
            equipments,
            fenestrationSurfs,
            globGeomRules,
            lights,
            locations,
            materialAirGap,
            materialNoMass,
            materials,
            peoples,
            zones,
            zonelists,
        ) = _order_objects(
            buildingSurfs,
            buildings,
            constr_list,
            constructions,
            equipments,
            fenestrationSurfs,
            globGeomRules,
            lights,
            locations,
            materialAirGap,
            materialNoMass,
            materials,
            peoples,
            zones,
            zonelists,
            ordered,
        )

        mat_name = _remove_low_conductivity(constructions, idf, materials)
        # Write LOCATION and GLOBALGEOMETRYRULES from IDF to lines (T3D) and
        # define if coordinate system is "Relative"
        coordSys = _write_location_geomrules(globGeomRules, lines, locations)

        # Determine if coordsSystem is "World" (all zones at (0,0,0))
        coordSys = _is_coordSys_world(coordSys, zones)

        # Change coordinates from relative to absolute for building surfaces
        _change_relative_coords(buildingSurfs, coordSys, idf)

        # Adds or changes adjacent surface if needed
        _add_change_adj_surf(buildingSurfs, idf)
        buildingSurfs = idf.idfobjects["BUILDINGSURFACE:DETAILED"]

        # region Write VARIABLEDICTONARY (Zone, BuildingSurf, FenestrationSurf)
        # from IDF to lines (T3D)

        # Get all surfaces having Outside boundary condition with the ground.
        # To be used to find the window's slopes
        n_ground = _get_ground_vertex(buildingSurfs)

        # Writing zones in lines
        schedule_as_input = True
        win_slope_dict = _write_zone_buildingSurf_fenestrationSurf(
            buildingSurfs,
            coordSys,
            fenestrationSurfs,
            idf,
            lines,
            n_ground,
            zones,
            schedule_as_input,
        )

        # Write CONSTRUCTION from IDF to lines (T3D)
        _write_constructions(constr_list, idf, lines, mat_name, materials)

        # Write CONSTRUCTION from IDF to lines, at the end of the T3D file
        _write_constructions_end(constr_list, idf, lines)

        # region Write WINDOWS chosen by the user (from Berkeley lab library) in
        # lines (T3D)
        # Get window from library
        # window = (win_id, description, design, u_win, shgc_win, t_sol_win,
        # rf_sol,
        #                 t_vis_win, lay_win, width, window_bunches[win_id],
        #                 and maybe tolerance)
        win_u_value = kwargs.get("u_value", 2.2)
        win_shgc = kwargs.get("shgc", 0.64)
        win_tvis = kwargs.get("t_vis", 0.8)
        win_tolerance = kwargs.get("tolerance", 0.05)
        window = choose_window(
            win_u_value, win_shgc, win_tvis, win_tolerance, window_lib
        )

        # Write windows in lines
        _write_window(lines, win_slope_dict, window)

        # Write window pool in lines
        _write_winPool(lines, window)

    def test_write_gains_conditioning(self, config, converttest):
        idf, idf_file, weather_file, window_lib, trnsidf_exe, template, _ = converttest

        # Run EnergyPlus Simulation
        ep_version = settings.ep_version
        outputs = [
            {
                "ep_object": "Output:Variable".upper(),
                "kwargs": dict(
                    Variable_Name="Zone Thermostat Heating Setpoint Temperature",
                    Reporting_Frequency="hourly",
                    save=True,
                ),
            },
            {
                "ep_object": "Output:Variable".upper(),
                "kwargs": dict(
                    Variable_Name="Zone Thermostat Cooling Setpoint Temperature",
                    Reporting_Frequency="hourly",
                    save=True,
                ),
            },
        ]
        _, idf = run_eplus(
            idf_file,
            weather_file,
            output_directory=None,
            ep_version=ep_version,
            output_report=None,
            prep_outputs=outputs,
            design_day=False,
            annual=True,
            expandobjects=True,
            return_idf=True,
        )

        # Outpout reports
        htm = idf.htm
        sql = idf.sql
        sql_file = idf.sql_file

        # Check if cache exists
        log_clear_names = False

        # Clean names of idf objects (e.g. 'MATERIAL')
        idf_2 = deepcopy(idf)
        clear_name_idf_objects(idf_2, log_clear_names)

        # Get old:new names equivalence
        old_new_names = pd.read_csv(
            os.path.join(
                settings.data_folder,
                Path(idf_file).basename().stripext() + "_old_new_names_equivalence.csv",
            )
        ).to_dict()

        # Read IDF_T3D template and write lines in variable
        lines = io.TextIOWrapper(io.BytesIO(settings.template_BUI)).readlines()

        # Get objects from IDF file
        (
            buildingSurfs,
            buildings,
            constructions,
            equipments,
            fenestrationSurfs,
            globGeomRules,
            lights,
            locations,
            materialAirGap,
            materialNoMass,
            materials,
            peoples,
            versions,
            zones,
            zonelists,
        ) = get_idf_objects(idf_2)

        # Write GAINS (People, Lights, Equipment) from IDF to lines (T3D)
        _write_gains(equipments, lights, lines, peoples, htm, old_new_names)

        # Gets schedules from IDF
        schedule_names, schedules = _get_schedules(idf_2)

        # Adds ground temperature to schedules
        adds_sch_ground(htm, schedule_names, schedules)

        # Adds "sch_setpoint_ZONES" to schedules
        df_heating_setpoint = ReportData.from_sqlite(
            sql_file, table_name="Zone Thermostat Heating Setpoint Temperature"
        )
        df_cooling_setpoint = ReportData.from_sqlite(
            sql_file, table_name="Zone Thermostat Cooling Setpoint Temperature"
        )
        # Heating
        adds_sch_setpoint(
            zones, df_heating_setpoint, old_new_names, schedule_names, schedules, "h"
        )
        # Cooling
        adds_sch_setpoint(
            zones, df_cooling_setpoint, old_new_names, schedule_names, schedules, "c"
        )

        schedule_as_input = True
        heat_dict, cool_dict = _write_conditioning(
            htm, lines, schedules, old_new_names, schedule_as_input
        )


@pytest.fixture(
    params=[
        "RefBldgWarehouseNew2004_Chicago.idf",
        "ASHRAE9012016_Warehouse_Denver.idf",
        "ASHRAE9012016_ApartmentMidRise_Denver.idf",
        "5ZoneGeometryTransform.idf",
    ]
)
def trnbuild_file(config, request):
    idf_file = get_eplus_dirs(settings.ep_version) / "ExampleFiles" / request.param
    idf_file = copy_file(idf_file, where=settings.cache_folder)

    yield idf_file


@pytest.mark.skipif(
    get_platform() > (10, 15, 0),
    reason="Skipping since wine 32bit can't run on MacOs >10.15 (Catalina)",
)
@pytest.mark.skipif(
    os.environ.get("CI", "False").lower() == "true",
    reason="Skipping this test on CI environment.",
)
class TestTrnBuild:
    def test_trnbuild_from_idf(self, config, trnbuild_file):
        # List files here

        window_file = "W74-lib.dat"
        template_dir = os.path.join("archetypal", "ressources")
        window_filepath = os.path.join(template_dir, window_file)
        weather_file = os.path.join(
            "tests", "input_data", "CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        )

        # prepare args (key=value). Key is a unique id for the runs (here the
        # file basename is used). Value is a dict of the function arguments
        kwargs_dict = {
            "ep_version": settings.ep_version,
            "u_value": 2.5,
            "shgc": 0.6,
            "t_vis": 0.78,
            "tolerance": 0.05,
            "fframe": 0.1,
            "uframe": 7.5,
            "ordered": True,
        }

        file = trnbuild_file
        convert_idf_to_trnbuild(
            idf_file=file,
            weather_file=weather_file,
            window_lib=window_filepath,
            template="tests/input_data/trnsys/NewFileTemplate.d18",
            trnsidf_exe="docker/trnsidf/trnsidf.exe",
            **kwargs_dict
        )

    @pytest.mark.win32
    def test_trnbuild_from_idf_parallel(self, config, trnbuild_file):
        # All IDF files
        # List files here
        files = trnbuild_file

        # window_file = 'W74-lib.dat'
        # window_filepath = os.path.join(file_upper_path, window_file)

        weather_file = os.path.join(
            "tests", "input_data", "CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        )

        # prepare args (key=value). Key is a unique id for the runs (here the
        # file basename is used). Value is a dict of the function arguments
        in_dict = {
            os.path.basename(file): dict(idf_file=file, weather_file=weather_file)
            for file in files
        }

        result = parallel_process(in_dict, convert_idf_to_trnbuild, 4, use_kwargs=True)

        assert not any(isinstance(a, Exception) for a in result.values())

    @pytest.mark.darwin
    @pytest.mark.linux
    def test_trnbuild_from_idf_parallel_darwin_or_linux(self, config):
        # All IDF files
        # List files here
        file_upper_path = os.path.join(
            get_eplus_dirs(settings.ep_version), "ExampleFiles"
        )
        files = [
            "RefBldgWarehouseNew2004_Chicago.idf",
            "ASHRAE9012016_Warehouse_Denver.idf",
            "ASHRAE9012016_ApartmentMidRise_Denver.idf",
            "5ZoneGeometryTransform.idf",
        ]

        weather_file = os.path.join(
            "tests", "input_data", "CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        )

        # prepare args (key=value). Key is a unique id for the runs (here the
        # file basename is used). Value is a dict of the function arguments
        in_dict = {
            os.path.basename(file): dict(
                idf_file=os.path.join(file_upper_path, file),
                weather_file=weather_file,
                template="tests/input_data/trnsys/NewFileTemplate.d18",
                trnsidf_exe="docker/trnsidf/trnsidf.exe",
            )
            for file in files
        }

        result = parallel_process(in_dict, convert_idf_to_trnbuild, 4, use_kwargs=True)
        [print(a) for a in result.values() if isinstance(a, Exception)]
        assert not any(isinstance(a, Exception) for a in result.values())

    @pytest.mark.win32
    def test_trnbuild_idf_win32(self, config):
        idf_file = "tests/input_data/trnsys/Building.idf"
        template = "tests/input_data/trnsys/NewFileTemplate.d18"
        res = trnbuild_idf(idf_file, template=template, nonum=True)

        assert res

    @pytest.mark.darwin
    @pytest.mark.linux
    @pytest.mark.xfail(
        not Path("docker/trnsidf/trnsidf.exe").exists(),
        reason="xfail since trnsidf.exe is not installed. This test can work if the "
        "trnsidf.exe is copied in ./docker/trnsidf",
    )
    def test_trnbuild_idf_darwin_or_linux(self, config):
        idf_file = "tests/input_data/trnsys/Building.idf"
        template = "tests/input_data/trnsys/NewFileTemplate.d18"
        trnsidf_exe = "docker/trnsidf/trnsidf.exe"
        res = trnbuild_idf(
            idf_file,
            template=template,
            dck=True,
            nonum=False,
            refarea=False,
            volume=False,
            capacitance=True,
            trnsidf_exe=trnsidf_exe,
        )

        assert res

    def test_trnbuild_from_simple_idf(self, config):
        # List files here

        window_file = "W74-lib.dat"
        template_dir = os.path.join("archetypal", "ressources")
        window_filepath = os.path.join(template_dir, window_file)
        weather_file = os.path.join(
            "tests", "input_data", "CAN_QC_Montreal-McTavish.716120_CWEC2016.epw"
        )

        # prepare args (key=value). Key is a unique id for the runs (here the
        # file basename is used). Value is a dict of the function arguments
        # WINDOW = 2-WSV_#3_Air
        kwargs_dict = {
            "ep_version": "9-2-0",
            "u_value": 1.62,
            "shgc": 0.64,
            "t_vis": 0.8,
            "tolerance": 0.05,
            "fframe": 0.0,
            "uframe": 0.5,
            "ordered": True,
        }

        file = os.path.join("tests", "input_data", "trnsys", "simple_2_zone.idf")
        convert_idf_to_trnbuild(
            idf_file=file,
            weather_file=weather_file,
            window_lib=window_filepath,
            template="tests/input_data/trnsys/NewFileTemplate.d18",
            trnsidf_exe="docker/trnsidf/trnsidf.exe",
            schedule_as_input=False,
            **kwargs_dict
        )
