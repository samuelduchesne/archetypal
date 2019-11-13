import io
import os

import pytest

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
)

# Function round to hundreds
from archetypal.trnsys import (
    _assert_files,
    _load_idf_file_and_clean_names,
    clear_name_idf_objects,
    _get_idf_objects,
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
    _write_schedules,
    _write_window,
    _write_winPool,
    _save_t3d,
    gains_to_b18,
)


class TestsConvert:
    """Tests convert_idf_to_trnbuild()"""

    @pytest.fixture(
        scope="class",
        params=[
            "RefBldgWarehousePost1980_v1.4_7.2_6A_USA_MN_MINNEAPOLIS.idf",
            "NECB 2011 - Warehouse.idf",
            "ASHRAE90.1_Warehouse_STD2004_Rochester.idf",
            "5ZoneGeometryTransform.idf",
        ],
    )
    def converttest(self, config, fresh_start, request):
        file = os.path.join("tests", "input_data", "trnsys", request.param)
        window_file = "W74-lib.dat"
        template_dir = os.path.join("archetypal", "ressources")
        window_filepath = os.path.join(template_dir, window_file)
        template_d18 = None
        trnsidf_exe = None  # 'docker/trnsidf/trnsidf.exe'

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

    def test_load_idf_file_and_clean_names(self, config, converttest):
        idf, idf_file, weather_file, window_lib, trnsidf_exe, template, _ = converttest
        log_clear_names = False
        idf_2 = _load_idf_file_and_clean_names(idf_file, log_clear_names)

    def test_get_save_write_schedules(self, config, converttest):
        output_folder = None
        idf, idf_file, weather_file, window_lib, trnsidf_exe, template, _ = converttest
        lines = io.TextIOWrapper(io.BytesIO(settings.template_BUI)).readlines()
        try:
            idf_file, weather_file, window_lib, output_folder, trnsidf_exe, template = _assert_files(
                idf_file, weather_file, window_lib, output_folder, trnsidf_exe, template
            )
        except:
            output_folder = os.path.relpath(settings.data_folder)
            print("Could not assert all paths exist - OK for this test")
        schedule_names, schedules = _get_schedules(idf)
        _yearlySched_to_csv(idf_file, output_folder, schedule_names, schedules)
        schedules_not_written = _write_schedules(lines, schedule_names, schedules)

    def test_write_version_and_building(self, config, converttest):
        idf, idf_file, weather_file, window_lib, trnsidf_exe, template, _ = converttest
        buildingSurfs, buildings, constructions, equipments, fenestrationSurfs, globGeomRules, lights, locations, materialAirGap, materialNoMass, materials, peoples, versions, zones, zonelists = _get_idf_objects(
            idf
        )
        lines = io.TextIOWrapper(io.BytesIO(settings.template_BUI)).readlines()
        _write_version(lines, versions)
        _write_building(buildings, lines)

    def test_write_idf_objects(self, config, converttest):
        idf, idf_file, weather_file, window_lib, trnsidf_exe, template, kwargs = (
            converttest
        )

        # Read IDF_T3D template and write lines in variable
        lines = io.TextIOWrapper(io.BytesIO(settings.template_BUI)).readlines()

        # Get objects from IDF file
        buildingSurfs, buildings, constructions, equipments, fenestrationSurfs, globGeomRules, lights, locations, materialAirGap, materialNoMass, materials, peoples, versions, zones, zonelists = _get_idf_objects(
            idf
        )

        # Get all construction EXCEPT fenestration ones
        constr_list = _get_constr_list(buildingSurfs)

        # If ordered=True, ordering idf objects
        ordered = True
        buildingSurfs, buildings, constr_list, constructions, equipments, fenestrationSurfs, globGeomRules, lights, locations, materialAirGap, materialNoMass, materials, peoples, zones, zonelists = _order_objects(
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
        win_slope_dict = _write_zone_buildingSurf_fenestrationSurf(
            buildingSurfs, coordSys, fenestrationSurfs, idf, lines, n_ground, zones
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

    def test_write_material(self, config, converttest):
        idf, idf_file, weather_file, window_lib, trnsidf_exe, template, _ = converttest

        # Read IDF_T3D template and write lines in variable
        lines = io.TextIOWrapper(io.BytesIO(settings.template_BUI)).readlines()

        # Get objects from IDF file
        buildingSurfs, buildings, constructions, equipments, fenestrationSurfs, globGeomRules, lights, locations, materialAirGap, materialNoMass, materials, peoples, versions, zones, zonelists = _get_idf_objects(
            idf
        )

        # Write LAYER from IDF to lines (T3D)
        _write_materials(lines, materialAirGap, materialNoMass, materials)

    def test_write_gains(self, config, converttest):
        idf, idf_file, weather_file, window_lib, trnsidf_exe, template, _ = converttest

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

        # Read IDF_T3D template and write lines in variable
        lines = io.TextIOWrapper(io.BytesIO(settings.template_BUI)).readlines()

        # Get objects from IDF file
        buildingSurfs, buildings, constructions, equipments, fenestrationSurfs, globGeomRules, lights, locations, materialAirGap, materialNoMass, materials, peoples, versions, zones, zonelists = _get_idf_objects(
            idf_2
        )

        # Write GAINS (People, Lights, Equipment) from IDF to lines (T3D)
        _write_gains(equipments, lights, lines, peoples, res, old_new_names)

    def test_save_t3d(self, config, converttest):
        output_folder = None
        idf, idf_file, weather_file, window_lib, trnsidf_exe, template, _ = converttest
        try:
            idf_file, weather_file, window_lib, output_folder, trnsidf_exe, template = _assert_files(
                idf_file, weather_file, window_lib, output_folder, trnsidf_exe, template
            )
        except:
            output_folder = os.path.relpath(settings.data_folder)
            print("Could not assert all paths exist - OK for this test")

        # Read IDF_T3D template and write lines in variable
        lines = io.TextIOWrapper(io.BytesIO(settings.template_BUI)).readlines()

        # Save T3D file at output_folder
        output_folder, t3d_path = _save_t3d(idf_file, lines, output_folder)


@pytest.fixture(
    params=[
        "RefBldgWarehousePost1980_v1.4_7.2_6A_USA_MN_MINNEAPOLIS.idf",
        "NECB 2011 - Warehouse.idf",
        "ASHRAE90.1_Warehouse_STD2004_Rochester.idf",
        "5ZoneGeometryTransform.idf",
    ]
)
def trnbuild_file(config, request):
    file_upper_path = Path("tests") / "input_data" / "trnsys"
    idf_file = file_upper_path / request.param
    idf_file = copy_file(idf_file, where=settings.cache_folder)

    yield idf_file


@pytest.mark.xfail(
    "TRAVIS" in os.environ and os.environ["TRAVIS"] == "true",
    reason="Skipping this test on Travis CI.",
)
def test_trnbuild_from_idf(config, trnbuild_file):
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
        "u_value": 2.5,
        "shgc": 0.6,
        "t_vis": 0.78,
        "tolerance": 0.05,
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
@pytest.mark.xfail(
    "TRAVIS" in os.environ and os.environ["TRAVIS"] == "true",
    reason="Skipping this test on Travis CI.",
)
def test_trnbuild_from_idf_parallel(config, trnbuild_file):
    # All IDF files
    idf_list = [
        "NECB 2011 - Full Service Restaurant.idf",
        "NECB 2011 - HighRise Apartment.idf",
        "NECB 2011 - Hospital.idf",
        "NECB 2011 - Large Hotel.idf",
        "NECB 2011 - Medium Office.idf",
        "NECB 2011 - MidRise Apartment.idf",
        "NECB 2011 - Outpatient.idf",
        "NECB 2011 - Primary School.idf",
        "NECB 2011 - Quick Service Restaurant.idf",
        "NECB 2011 - Retail Standalone.idf",
        "NECB 2011 - Retail Stripmall.idf",
        "NECB 2011 - Secondary School.idf",
        "NECB 2011 - Small Hotel.idf",
        "NECB 2011 - Small Office.idf",
        "NECB 2011 - Warehouse.idf",
        "ASHRAE90.1_ApartmentHighRise_STD2004_Rochester.idf",
        "ASHRAE90.1_ApartmentMidRise_STD2004_Rochester.idf",
        "ASHRAE90.1_Hospital_STD2004_Rochester.idf",
        "ASHRAE90.1_HotelLarge_STD2004_Rochester.idf",
        "ASHRAE90.1_HotelSmall_STD2004_Rochester.idf",
        "ASHRAE90.1_OfficeLarge_STD2004_Rochester.idf",
        "ASHRAE90.1_OfficeMedium_STD2004_Rochester.idf",
        "ASHRAE90.1_OfficeSmall_STD2004_Rochester.idf",
        "ASHRAE90.1_OutPatientHealthCare_STD2004_Rochester.idf",
        "ASHRAE90.1_RestaurantFastFood_STD2004_Rochester.idf",
        "ASHRAE90.1_RestaurantSitDown_STD2004_Rochester.idf",
        "ASHRAE90.1_RetailStandalone_STD2004_Rochester.idf",
        "ASHRAE90.1_RetailStripmall_STD2004_Rochester.idf",
        "ASHRAE90.1_SchoolPrimary_STD2004_Rochester.idf",
        "ASHRAE90.1_SchoolSecondary_STD2004_Rochester.idf",
        "ASHRAE90.1_Warehouse_STD2004_Rochester.idf",
    ]
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
@pytest.mark.xfail(
    "TRAVIS" in os.environ and os.environ["TRAVIS"] == "true",
    reason="Skipping this test on Travis CI.",
)
def test_trnbuild_from_idf_parallel_darwin_or_linux(config):
    # All IDF files
    idf_list = [
        "NECB 2011 - Full Service Restaurant.idf",
        "NECB 2011 - HighRise Apartment.idf",
        "NECB 2011 - Hospital.idf",
        "NECB 2011 - Large Hotel.idf",
        "NECB 2011 - Medium Office.idf",
        "NECB 2011 - MidRise Apartment.idf",
        "NECB 2011 - Outpatient.idf",
        "NECB 2011 - Primary School.idf",
        "NECB 2011 - Quick Service Restaurant.idf",
        "NECB 2011 - Retail Standalone.idf",
        "NECB 2011 - Retail Stripmall.idf",
        "NECB 2011 - Secondary School.idf",
        "NECB 2011 - Small Hotel.idf",
        "NECB 2011 - Small Office.idf",
        "NECB 2011 - Warehouse.idf",
        "ASHRAE90.1_ApartmentHighRise_STD2004_Rochester.idf",
        "ASHRAE90.1_ApartmentMidRise_STD2004_Rochester.idf",
        "ASHRAE90.1_Hospital_STD2004_Rochester.idf",
        "ASHRAE90.1_HotelLarge_STD2004_Rochester.idf",
        "ASHRAE90.1_HotelSmall_STD2004_Rochester.idf",
        "ASHRAE90.1_OfficeLarge_STD2004_Rochester.idf",
        "ASHRAE90.1_OfficeMedium_STD2004_Rochester.idf",
        "ASHRAE90.1_OfficeSmall_STD2004_Rochester.idf",
        "ASHRAE90.1_OutPatientHealthCare_STD2004_Rochester.idf",
        "ASHRAE90.1_RestaurantFastFood_STD2004_Rochester.idf",
        "ASHRAE90.1_RestaurantSitDown_STD2004_Rochester.idf",
        "ASHRAE90.1_RetailStandalone_STD2004_Rochester.idf",
        "ASHRAE90.1_RetailStripmall_STD2004_Rochester.idf",
        "ASHRAE90.1_SchoolPrimary_STD2004_Rochester.idf",
        "ASHRAE90.1_SchoolSecondary_STD2004_Rochester.idf",
        "ASHRAE90.1_Warehouse_STD2004_Rochester.idf",
    ]
    # List files here
    file_upper_path = os.path.join("tests", "input_data", "trnsys")
    files = [
        "RefBldgWarehousePost1980_v1.3_5" ".0_4A_USA_MD_BALTIMORE.idf",
        "NECB 2011 - Warehouse.idf",
        "ASHRAE90.1_Warehouse_STD2004_Rochester.idf",
        "ASHRAE90.1_ApartmentMidRise_STD2004_Rochester.idf",
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
@pytest.mark.xfail(
    "TRAVIS" in os.environ and os.environ["TRAVIS"] == "true",
    reason="Skipping this test on Travis CI.",
)
def test_trnbuild_idf_win32(config):
    idf_file = "tests/input_data/trnsys/Building.idf"
    template = "tests/input_data/trnsys/NewFileTemplate.d18"
    res = trnbuild_idf(idf_file, template=template, nonum=True)

    assert res


@pytest.mark.darwin
@pytest.mark.linux
@pytest.mark.xfail(
    "TRAVIS" in os.environ and os.environ["TRAVIS"] == "true",
    reason="Skipping this test on Travis CI.",
)
def test_trnbuild_idf_darwin_or_linux(config):
    idf_file = "tests/input_data/trnsys/Building.idf"
    weather_file = os.path.join(
        "tests", "input_data", "CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    )
    template = "tests/input_data/trnsys/NewFileTemplate.d18"
    trnsidf_exe = "docker/trnsidf/trnsidf.exe"
    res = trnbuild_idf(
        idf_file,
        weather_file,
        template=template,
        dck=True,
        nonum=False,
        refarea=False,
        volume=False,
        capacitance=True,
        trnsidf_exe=trnsidf_exe,
    )

    assert res

@pytest.mark.xfail(
    "TRAVIS" in os.environ and os.environ["TRAVIS"] == "true",
    reason="Skipping this test on Travis CI.",
)
def test_trnbuild_from_simple_idf(config):
    # List files here

    window_file = "W74-lib.dat"
    template_dir = os.path.join("archetypal", "ressources")
    window_filepath = os.path.join(template_dir, window_file)
    weather_file = os.path.join(
        "tests", "input_data", "CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    )

    # prepare args (key=value). Key is a unique id for the runs (here the
    # file basename is used). Value is a dict of the function arguments
    # WINDOW = 2-WSV_#3_Air
    kwargs_dict = {
        "u_value": 1.62,
        "shgc": 0.64,
        "t_vis": 0.8,
        "tolerance": 0.05,
        "fframe": 0.0,
        "uframe": 0.5,
        "ordered": True,
    }

    file = os.path.join(
        "tests", "input_data", "trnsys", "simple_2_zone.idf"
    )
    convert_idf_to_trnbuild(
        idf_file=file,
        weather_file=weather_file,
        window_lib=window_filepath,
        template="tests/input_data/trnsys/NewFileTemplate.d18",
        trnsidf_exe="docker/trnsidf/trnsidf.exe",
        **kwargs_dict
    )
