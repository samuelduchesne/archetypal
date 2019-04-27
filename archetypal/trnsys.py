import logging as lg
import numpy as np
import pandas as pd
import os
import time
import uuid
from eppy import modeleditor
from geomeppy.geom.polygons import Polygon3D
from geomeppy.utilities import almostequal
from collections import OrderedDict

import archetypal as ar
from archetypal import log, Schedule, run_eplus, copy_file, schedule_types


def clear_name_idf_objects(idfFile):
    """Clean names of IDF objects :
        - replace special characters or whitespaces with "_"
        - limits length to 13 characters
        - replace name by an unique id if needed

    Args:
        idfFile (eppy.modeleditor.IDF): IDF object where to clean names

    Returns:

    """
    objs = ['MATERIAL', 'MATERIAL:NOMASS', 'MATERIAL:AIRGAP', 'CONSTRUCTION',
            'FENESTRATIONSURFACE:DETAILED', 'BUILDINGSURFACE:DETAILED', 'ZONE',
            'BUILDING', 'SITE:LOCATION', 'SCHEDULE:YEAR', 'SCHEDULE:WEEK:DAILY',
            'SCHEDULE:DAY:INTERVAL', 'SCHEDULE:COMPACT', 'PEOPLE', 'LIGHTS',
            'ELECTRICEQUIPMENT']
    uniqueList = []

    # For all categories of objects in the IDF file
    for obj in idfFile.idfobjects:
        epObjects = idfFile.idfobjects[obj]

        # For all objects in Category
        for epObject in epObjects:
            # Do not take fenestration, to be treated later
            try:
                fenestration = [s for s in ['fenestration', 'shgc', 'window'] if
                                s in epObject.Name.lower()]
            except:
                fenestration = []
            if not fenestration:
                try:
                    old_name = epObject.Name
                    # clean old name by removing spaces, "-", period, "{", "}", doubleunderscore
                    new_name = old_name.replace(" ", "_").replace("-",
                                                                  "_").replace(
                        ".", "_").replace("{", "").replace("}", "").replace(
                        "__",
                        "_")
                    if len(new_name) > 13:
                        # Trnbuild doen not like names longer than 13 characters
                        # Replace with unique ID
                        new_name = uuid.uuid4().hex[:13]

                        # Make sure uuid does not already exist
                        while new_name in uniqueList:
                            new_name = uuid.uuid4().hex[:13]

                        uniqueList.append(new_name)

                    # print("changed layer {} with {}".format(old_name, new_name))
                    modeleditor.rename(idfFile, obj, old_name, new_name)
                except:
                    pass
            else:
                continue


def zone_origin(zone_object):
    """ Return coordinates of a zone

    Args:
        zone_object (EpBunch): zone element in zone list

    Returns: Coordinates [X, Y, Z] of the zone in a list

    """
    return [zone_object.X_Origin, zone_object.Y_Origin, zone_object.Z_Origin]


def closest_coords(surfList, to=[0, 0, 0]):
    """Find closest coordinates to given ones

    Args:
        surfList (idf_MSequence): list of surface with coordinates of each one
        to (list): list of coordinates we want to calculate the distance from

    Returns: the closest point (its coordinates x, y, z) to the point chosen
        (input "to")

    """
    from scipy.spatial import cKDTree
    size = recursive_len(
        [buildingSurf.coords for buildingSurf in surfList])
    tuple_list = []
    for surf in surfList:
        for i in range(0, len(surf.coords)):
            tuple_list.append(surf.coords[i])

    nbdata = np.array(tuple_list)
    # nbdata = np.array([buildingSurf.coords for buildingSurf in surfList]).reshape(size,len(to))
    btree = cKDTree(data=nbdata, compact_nodes=True, balanced_tree=True)
    dist, idx = btree.query(np.array(to).T, k=1)
    x, y, z = nbdata[idx]
    return x, y, z


def recursive_len(item):
    """Calculate the number of elments in nested list

    Args:
        item (list): list of lists (i.e. nested list)

    Returns: Total number of elements in nested list

    """
    if type(item) == list:
        return sum(recursive_len(subitem) for subitem in item)
    else:
        return 1


def rotate(l, n):
    """

    Args:
        l (list): list to rotate
        n (int): number to shift list to the left

    Returns (list): list shifted

    """
    return l[n:] + l[:n]


def parse_window_lib(window_file_path):
    # Read window library and write lines in variable
    all_lines = open(window_file_path).readlines()

    # Select list of windows at the end of the file
    end = '*** END OF LIBRARY ***'
    indice_end = [k for k, s in enumerate(all_lines) if
                  end in s]

    window_list = all_lines[indice_end[0] + 1:]

    # Delete asterisk lines
    asterisk = '*'
    indices_asterisk = [k for k, line in enumerate(window_list) if
                        asterisk in line]
    window_list = [','.join(line.split()) for i, line in enumerate(window_list)
                   if
                   i not in indices_asterisk]

    # Save lines_for_df in text file
    # User did not provide an output folder path. We use the default setting
    output_folder = ar.settings.data_folder

    if not os.path.isdir(output_folder):
        os.mkdir(output_folder)

    with open(os.path.join(output_folder, "winPOOL.txt"),
              "w") as converted_file:
        for line in window_list:
            converted_file.write(str(line) + '\n')

    df_windows = pd.read_csv(os.path.join(output_folder, "winPOOL.txt"),
                             header=None)
    columns = ['WinID', 'Description', 'Design', 'u_value', 'g_value', 'T_sol',
               'Rf_sol', 't_vis', 'Lay', 'Width']
    df_windows.columns = columns

    # Select list of windows with all their characteristics (bunch)
    bunch_delimiter = 'BERKELEY LAB WINDOW v7.4.6.0  DOE-2 Data File : Multi Band Calculation : generated with Trnsys18.std\n'
    indices_bunch = [k for k, s in enumerate(all_lines) if
                     s == bunch_delimiter]
    detailed_windows = all_lines[0:indice_end[0]]

    # 1 window = 55 lines
    window_count = (len(detailed_windows) - 1) / 55
    bunches_list = list(chunks(detailed_windows, 55))

    bunches = dict(get_window_id(bunches_list))

    return df_windows, bunches


def get_window_id(bunches):
    """Return bunch of window properties with their window id"""
    id_line = 'Window ID   :'
    for bunch in bunches:
        for line in bunch:
            if id_line in line:
                _, value = line.split(':')
                value = int(value.strip())
                yield value, bunch


def chunks(l, n):
    """Yield successive n-sized chunks from l"""
    for i in range(0, len(l), n):
        yield l[i:i + n]


def choose_window(u_value, shgc, t_vis, tolerance, window_lib_path):
    """Return window object from TRNBuild library

    Args:
        u_value (float): U_value of the glazing
        shgc (float): SHGC of the glazing
        t_vis (float): Visible transmittance of the glazing
        tolerance (float): Maximum tolerance on u_value, shgc and tvis
            wanted by the user
        window_lib_path (.dat file): window library from Berkeley lab

    Returns (tuple): The window chosen : window_ID, the "bunch" of
        description/properties from Berkeley lab, window u_value, window shgc,
        and window visible transmittance. If tolerance not respected return new
        tolerance used to find a window.

    """
    # Init "warn" variable (0 or 1) to log a warning if tolerance not respected
    warn = 0

    # Making sure u_value, shgc and tvis are float
    if not isinstance(u_value, float):
        u_value = float(u_value)
    if not isinstance(shgc, float):
        shgc = float(shgc)
    if not isinstance(t_vis, float):
        t_vis = float(t_vis)
    if not isinstance(t_vis, float):
        t_vis = float(t_vis)

    # Parse window library
    df_windows, window_bunches = parse_window_lib(window_lib_path)

    # Find window(s) in the tolerance limit
    cond1 = (df_windows['u_value'] <= u_value * (1 + tolerance)) & (
            df_windows['u_value'] >= u_value * (1 - tolerance))
    cond2 = (df_windows['g_value'] <= shgc * (1 + tolerance)) & (
            df_windows['g_value'] >= shgc * (1 - tolerance))
    cond3 = (df_windows['t_vis'] <= t_vis * (1 + tolerance)) & (
            df_windows['t_vis'] >= t_vis * (1 - tolerance))

    # Every window's IDs satisfying the tolerance
    win_ids = df_windows.loc[(cond1 & cond2 & cond3), 'WinID']

    # If nothing found, increase the tolerance
    while win_ids.empty:
        warn = 1
        tolerance += 0.01
        cond1 = (df_windows['u_value'] <= u_value * (1 + tolerance)) & (
                df_windows['u_value'] >= u_value * (1 - tolerance))
        cond2 = (df_windows['g_value'] <= shgc * (1 + tolerance)) & (
                df_windows['g_value'] >= shgc * (1 - tolerance))
        cond3 = (df_windows['t_vis'] <= t_vis * (1 + tolerance)) & (
                df_windows['t_vis'] >= t_vis * (1 - tolerance))
        win_ids = df_windows.loc[(cond1 & cond2 & cond3), 'WinID']

    # If several windows found, get the one with the minimal square error sum.
    best_window_index = df_windows.loc[win_ids.index, :].apply(
        lambda x: (x.u_value - u_value) ** 2 + (x.g_value - shgc) ** 2 + (
                x.t_vis - t_vis) ** 2, axis=1).idxmin()
    win_id, description, design, u_win, shgc_win, t_sol_win, rf_sol_win, t_vis_win, lay_win, width = \
        df_windows.loc[
            best_window_index, ['WinID', 'Description', 'Design', 'u_value',
                                'g_value', 'T_sol', 'Rf_sol', 't_vis', 'Lay',
                                'Width']]

    # If warn = 1 (tolerance not respected) return tolerance
    if warn:
        return (
            win_id, description, design, u_win, shgc_win, t_sol_win, rf_sol_win,
            t_vis_win, lay_win, width, window_bunches[win_id], tolerance)
    else:
        return (
            win_id, description, design, u_win, shgc_win, t_sol_win, rf_sol_win,
            t_vis_win, lay_win, width, window_bunches[win_id])


def convert_idf_to_t3d(idf_file, window_lib, output_folder=None):
    """ Convert IDF file to T3D file to be able to load it in TRNBuild

    Args:
        idf (str): File path of IDF file to convert to T3D
        window_lib (str): File path of the window library (from Berkeley Lab)
        output_folder (str): location where output file will be saved. If None,
            saves to settings.data_folder

    Returns:
        (idf file) : Input file for TRNBuild

    """

    start_time = time.time()
    # Load IDF file(s)
    idf_dict = ar.load_idf(idf_file)
    idf = idf_dict[os.path.basename(idf_file)]
    log("IDF files loaded in {:,.2f} seconds".format(time.time() - start_time),
        lg.INFO, name="CoverterLog", filename="CoverterLog", avoid_console=True)

    # Load IDF_T3D template
    ori_idf_filename = "originBUISketchUp.idf"
    ori_idf_filepath = os.path.join("..", "tests", "input_data", "trnsys",
                                    ori_idf_filename)
    # Read IDF_T3D template and write lines in variable
    lines = open(ori_idf_filepath).readlines()

    # Clean names of idf objects (e.g. 'MATERIAL')
    start_time = time.time()
    # clear_name_idf_objects(idf)
    log("Cleaned IDF object names in {:,.2f} seconds".format(
        time.time() - start_time), lg.INFO, name="CoverterLog",
        filename="CoverterLog")

    # Get objects from IDF file
    materials = idf.idfobjects['MATERIAL']
    materialNoMass = idf.idfobjects['MATERIAL:NOMASS']
    materialAirGap = idf.idfobjects['MATERIAL:AIRGAP']
    versions = idf.idfobjects['VERSION']
    buildings = idf.idfobjects['BUILDING']
    locations = idf.idfobjects['SITE:LOCATION']
    globGeomRules = idf.idfobjects['GLOBALGEOMETRYRULES']
    constructions = idf.idfobjects['CONSTRUCTION']
    fenestrationSurfs = idf.idfobjects['FENESTRATIONSURFACE:DETAILED']
    buildingSurfs = idf.idfobjects['BUILDINGSURFACE:DETAILED']
    zones = idf.idfobjects['ZONE']
    scheduleYear = idf.idfobjects['SCHEDULE:YEAR']
    scheduleWeek = idf.idfobjects['SCHEDULE:WEEK:DAILY']
    scheduleDay = idf.idfobjects['SCHEDULE:DAY:INTERVAL']
    peoples = idf.idfobjects['PEOPLE']
    lights = idf.idfobjects['LIGHTS']
    equipments = idf.idfobjects['ELECTRICEQUIPMENT']

    # start_time = time.time()
    # schedule_names = []
    # used_schedules = idf.get_used_schedules(yearly_only=True)
    # schedules = {}
    #
    # for schedule_name in used_schedules:
    #     s = Schedule(idf, sch_name=schedule_name,
    #                  start_day_of_the_week=idf.day_of_week_for_start_day)
    #
    #     schedule_names.append(schedule_name)
    #     schedules[schedule_name] = {}
    #     year, weeks, days = s.to_year_week_day()
    #     schedules[schedule_name]['year'] = year
    #     schedules[schedule_name]['weeks'] = weeks
    #     schedules[schedule_name]['days'] = days
    #
    # log("Got yearly, weekly and daily schedules in {:,.2f} seconds".format(
    #     time.time() - start_time), lg.INFO, name="CoverterLog",
    #     filename="CoverterLog")

    # Get materials with resistance lower than 0.0007
    material_low_res = []
    for material in materials:
        if material.Thickness / (
                material.Conductivity * 3.6) < 0.0007:
            material_low_res.append(material)

    # Remove materials with resistance lower than 0.0007 from IDF
    mat_name = []
    for mat in material_low_res:
        mat_name.append(mat.Name)
        idf.removeidfobject(mat)

    # Get constructions with only materials with resistance lower than 0.0007
    construct_low_res = []
    for i in range(0, len(constructions)):
        if len(constructions.list2[i]) == 3 and constructions.list2[i][
            2] in mat_name:
            construct_low_res.append(constructions[i])

    # Remove constructions with only materials with resistance lower than 0.0007 from IDF
    for construct in construct_low_res:
        idf.removeidfobject(construct)

    # Write data from IDF file to T3D file
    start_time = time.time()

    # Write VERSION from IDF to lines (T3D)
    # Get line number where to write
    with open(ori_idf_filepath) as ori:
        versionNum = ar.checkStr(ori,
                                 'ALL OBJECTS IN CLASS: VERSION')
    # Writing VERSION infos to lines
    for i in range(0, len(versions)):
        lines.insert(versionNum,
                     ",".join(str(item) for item in versions.list2[i]) + ';')

    # Write BUILDING from IDF to lines (T3D)
    # Get line number where to write
    buildingNum = ar.checkStr(lines,
                              'ALL OBJECTS IN CLASS: BUILDING')
    # Writing BUILDING infos to lines
    for building in buildings:
        lines.insert(buildingNum, building)

    # Write LOCATION and GLOBALGEOMETRYRULES from IDF to lines (T3D)
    # Get line number where to write
    locationNum = ar.checkStr(lines,
                              'ALL OBJECTS IN CLASS: LOCATION')

    # Writing GLOBALGEOMETRYRULES infos to lines
    for globGeomRule in globGeomRules:
        # Change Geometric rules from Relative to Absolute
        coordSys = "Absolute"
        if globGeomRule.Coordinate_System == 'Relative':
            coordSys = "Relative"
            globGeomRule.Coordinate_System = 'Absolute'

        if globGeomRule.Daylighting_Reference_Point_Coordinate_System == 'Relative':
            globGeomRule.Daylighting_Reference_Point_Coordinate_System = 'Absolute'

        if globGeomRule.Rectangular_Surface_Coordinate_System == 'Relative':
            globGeomRule.Rectangular_Surface_Coordinate_System = 'Absolute'

        lines.insert(locationNum, globGeomRule)

    # Writing LOCATION infos to lines
    for location in locations:
        lines.insert(locationNum, location)

    # Determine if coordsSystem is "World" (all zones at (0,0,0))
    X_zones = []
    Y_zones = []
    Z_zones = []
    # Store all zones coordinates in lists
    for zone in zones:
        x, y, z = zone_origin(zone)
        X_zones.append(x)
        Y_zones.append(y)
        Z_zones.append(z)
    # If 2 zones have same coords and are equal to 0 -> coordSys = "World"
    if X_zones[0] == X_zones[1] and Y_zones[0] == Y_zones[1] and \
            Z_zones[0] == Z_zones[1] and X_zones[0] == 0 and Y_zones[0] == 0 \
            and Z_zones[0] == 0:
        coordSys = "World"

    # region Write VARIABLEDICTONARY (Zone, BuildingSurf, FenestrationSurf) from IDF to lines (T3D)
    # Get line number where to write
    variableDictNum = ar.checkStr(lines,
                                  'ALL OBJECTS IN CLASS: OUTPUT:VARIABLEDICTIONARY')

    # Writing zones in lines
    for zone in zones:
        zone.Direction_of_Relative_North = 0.0
        zone.Multiplier = 1
        # Coords of zone
        incrX, incrY, incrZ = zone_origin(zone)

        # Writing fenestrationSurface:Detailed in lines
        for fenestrationSurf in fenestrationSurfs:
            surfName = fenestrationSurf.Building_Surface_Name
            indiceSurf = [k for k, s in enumerate(buildingSurfs) if
                          surfName == s.Name]
            if buildingSurfs[indiceSurf[0]].Zone_Name == zone.Name:

                fenestrationSurf.Construction_Name = "EXT_WINDOW1"
                fenestrationSurf.Number_of_Vertices = len(
                    fenestrationSurf.coords)

                # Change coordinates from relative to absolute
                if coordSys == 'Relative':

                    # Add zone coordinates to X, Y, Z vectors to fenestration surface
                    for j in range(1, len(
                                fenestrationSurf.coords) + 1):
                        fenestrationSurf["Vertex_" + str(j) + "_Xcoordinate"] = \
                            fenestrationSurf[
                                "Vertex_" + str(j) + "_Xcoordinate"] + incrX
                        fenestrationSurf["Vertex_" + str(j) + "_Ycoordinate"] = \
                            fenestrationSurf[
                                "Vertex_" + str(j) + "_Ycoordinate"] + incrY
                        fenestrationSurf["Vertex_" + str(j) + "_Zcoordinate"] = \
                            fenestrationSurf[
                                "Vertex_" + str(j) + "_Zcoordinate"] + incrZ

                lines.insert(variableDictNum + 2, fenestrationSurf)

        # Writing buildingSurface: Detailed in lines
        surfList = []
        for i in range(0, len(buildingSurfs)):
            # Change Outside Boundary Condition and Objects
            if buildingSurfs[i].Zone_Name == zone.Name:
                buildingSurfs[i].Number_of_Vertices = len(
                    buildingSurfs[i].coords)
                surfList.append(buildingSurfs[i])
                if 'surface' in buildingSurfs[
                    i].Outside_Boundary_Condition.lower():
                    buildingSurfs[i].Outside_Boundary_Condition = "Zone"
                    surface = buildingSurfs[i].Outside_Boundary_Condition_Object
                    indiceSurf = [k for k, s in enumerate(buildingSurfs) if
                                  surface == s.Name]
                    indiceZone = [k for k, s in enumerate(zones) if
                                  buildingSurfs[
                                      indiceSurf[0]].Zone_Name == s.Name]
                    buildingSurfs[i].Outside_Boundary_Condition_Object = zones[
                        indiceZone[0]].Name

                    # Polygon from vector's adjacent surfaces
                    poly1 = Polygon3D(buildingSurfs[i].coords)
                    poly2 = Polygon3D(buildingSurfs[indiceSurf[0]].coords)
                    # Normal vectors of each polygon
                    n1 = poly1.normal_vector
                    n2 = poly2.normal_vector
                    # Verify if normal vectors of adjacent surfaces have
                    # opposite directions
                    if (n1 + n2).x != 0 or (n1 + n2).y != 0 or (n1 + n2).z != 0:
                        for j, k in zip(range(1, len(
                                buildingSurfs[i].coords) + 1), range(
                                len(buildingSurfs[i].coords), 0, -1)):
                            buildingSurfs[indiceSurf[0]][
                                "Vertex_" + str(j) + "_Xcoordinate"] \
                                = buildingSurfs[i][
                                      "Vertex_" + str(k) + "_Xcoordinate"]
                            buildingSurfs[indiceSurf[0]][
                                "Vertex_" + str(j) + "_Ycoordinate"] \
                                = buildingSurfs[i][
                                      "Vertex_" + str(k) + "_Ycoordinate"]
                            buildingSurfs[indiceSurf[0]][
                                "Vertex_" + str(j) + "_Zcoordinate"] \
                                = buildingSurfs[i][
                                      "Vertex_" + str(k) + "_Zcoordinate"]

                if 'ground' in buildingSurfs[
                    i].Outside_Boundary_Condition.lower():
                    buildingSurfs[
                        i].Outside_Boundary_Condition_Object = "BOUNDARY=INPUT 1*TGROUND"

                if 'adiabatic' in buildingSurfs[
                    i].Outside_Boundary_Condition.lower():
                    buildingSurfs[
                        i].Outside_Boundary_Condition = "OtherSideCoefficients"
                    buildingSurfs[
                        i].Outside_Boundary_Condition_Object = "BOUNDARY=IDENTICAL"

                # Change coordinates from relative to absolute
                if coordSys == 'Relative':
                    # Add zone coordinates to X, Y, Z vectors
                    for j in range(1, len(buildingSurfs[i].coords) + 1):
                        buildingSurfs[i]["Vertex_" + str(j) + "_Xcoordinate"] \
                            = buildingSurfs[i][
                                  "Vertex_" + str(j) + "_Xcoordinate"] \
                              + incrX
                        buildingSurfs[i]["Vertex_" + str(j) + "_Ycoordinate"] \
                            = buildingSurfs[i][
                                  "Vertex_" + str(j) + "_Ycoordinate"] \
                              + incrY
                        buildingSurfs[i]["Vertex_" + str(j) + "_Zcoordinate"] \
                            = buildingSurfs[i][
                                  "Vertex_" + str(j) + "_Zcoordinate"] \
                              + incrZ

                lines.insert(variableDictNum + 2, buildingSurfs[i])

        # Change coordinates from world (all zones to 0) to absolute
        if coordSys == 'World':
            zone.X_Origin, zone.Y_Origin, zone.Z_Origin = closest_coords(
                surfList, to=zone_origin(zone))

        lines.insert(variableDictNum + 2, zone)
    # endregion

    # region Write CONSTRUCTION from IDF to lines (T3D)
    # Get line number where to write
    constructionNum = ar.checkStr(lines, 'C O N S T R U C T I O N')

    # Writing CONSTRUCTION in lines
    for i in range(0, len(constructions.list2)):

        # Except fenestration construction
        fenestration = [s for s in ['fenestration', 'shgc', 'window'] if
                        s in constructions.list2[i][1].lower()]

        if not fenestration:
            lines.insert(constructionNum + 1,
                         '!-CONSTRUCTION ' + constructions[i].Name + '\n')
        else:
            continue

        # Create lists to append with layers and thickness of construction
        layerList = []
        thickList = []

        for j in range(2, len(constructions.list2[i])):

            if constructions.list2[i][j] not in mat_name:

                indiceMat = [k for k, s in enumerate(materials) if
                             constructions.list2[i][j] == s.Name]

                if not indiceMat:
                    thickList.append(0.0)
                else:
                    thickList.append(materials[indiceMat[0]].Thickness)

                layerList.append(constructions.list2[i][j])

            else:
                continue

        lines.insert(constructionNum + 2, '!- LAYERS = ' + " ".join(
            str(item) for item in layerList[::-1]) + '\n')
        lines.insert(constructionNum + 3, '!- THICKNESS= ' + " ".join(
            str(item) for item in thickList[::-1]) + '\n')
        lines.insert(constructionNum + 4,
                     '!- ABS-FRONT= 0.4   : ABS-BACK= 0.5\n')
        lines.insert(constructionNum + 5,
                     '!- EPS-FRONT= 0.9   : EPS-BACK= 0.9\n')

        basement = [s for s in ['basement', 'floor'] if
                    s in constructions.list2[i][1].lower()]
        if not basement:
            lines.insert(constructionNum + 6, '!- HFRONT   = 11 : HBACK= 64\n')
        else:
            lines.insert(constructionNum + 6, '!- HFRONT   = 11 : HBACK= 0\n')
    # endregion

    # Write CONSTRUCTION from IDF to lines, at the end of the T3D file
    # Get line number where to write
    constructionEndNum = ar.checkStr(lines,
                                     'ALL OBJECTS IN CLASS: CONSTRUCTION')

    # Writing CONSTRUCTION infos to lines
    for i in range(0, len(constructions)):

        # Except fenestration construction
        fenestration = [s for s in ['fenestration', 'shgc', 'window'] if
                        s in constructions.list2[i][1].lower()]
        if not fenestration:
            lines.insert(constructionEndNum, constructions[i])
        else:
            continue

    # region Write LAYER from IDF to lines (T3D)
    # Get line number where to write
    layerNum = ar.checkStr(lines, 'L a y e r s')

    # Writing MATERIAL infos to lines
    listLayerName = []
    for i in range(0, len(materials)):
        lines.insert(layerNum + 1, '!-LAYER ' + materials[i].Name + '\n')
        listLayerName.append(materials[i].Name)

        lines.insert(layerNum + 2, '!- CONDUCTIVITY=' + str(
            round(materials[i].Conductivity * 3.6, 4)) +
                     ' : CAPACITY= ' + str(
            round(materials[i].Specific_Heat / 1000, 4)) + ' : DENSITY= ' +
                     str(round(materials[i].Density,
                               4)) + ' : PERT= 0 : PENRT= 0\n')

    # Writing MATERIAL:NOMASS infos to lines
    for i in range(0, len(materialNoMass)):

        duplicate = [s for s in listLayerName if s == materialNoMass[i].Name]
        if not duplicate:
            lines.insert(layerNum + 1,
                         '!-LAYER ' + materialNoMass[i].Name + '\n')
            listLayerName.append(materialNoMass[i].Name)

            lines.insert(layerNum + 2, '!- RESISTANCE=' + str(
                round(materialNoMass[i].Thermal_Resistance / 3.6, 4)) +
                         ' : PERT= 0 : PENRT= 0\n')
        else:
            continue

    # Writing MATERIAL:AIRGAP infos to lines
    for i in range(0, len(materialAirGap)):

        duplicate = [s for s in listLayerName if s == materialAirGap[i].Name]
        if not duplicate:
            lines.insert(layerNum + 1,
                         '!-LAYER ' + materialAirGap[i].Name + '\n')
            listLayerName.append(materialAirGap[i].Name)

            lines.insert(layerNum + 2, '!- RESISTANCE=' + str(
                round(materialAirGap[i].Thermal_Resistance / 3.6, 4)) +
                         ' : PERT= 0 : PENRT= 0\n')
        else:
            continue
    # endregion

    # region Write GAINS (People, Lights, Equipment) from IDF to lines (T3D)
    # Get line number where to write
    gainNum = ar.checkStr(lines, 'G a i n s')

    # Writing PEOPLE gains infos to lines
    schedule_list_people = []
    for i in range(0, len(peoples)):

        schYearName = peoples[i].Activity_Level_Schedule_Name
        indiceSchYear = [k for k, s in enumerate(scheduleYear) if
                         peoples[i].Activity_Level_Schedule_Name == s.Name]
        schWeekName = scheduleYear[indiceSchYear[0]].ScheduleWeek_Name_1
        indiceSchWeek = [k for k, s in enumerate(scheduleWeek) if scheduleYear[
            indiceSchYear[0]].ScheduleWeek_Name_1 == s.Name]
        weekSch = list(
            OrderedDict.fromkeys(scheduleWeek.list2[indiceSchWeek[0]][2::]))

        lines.insert(gainNum + 1,
                     'GAIN PEOPLE' + '_' + peoples[i].Name + '\n')

        if peoples[i].Number_of_People_Calculation_Method == "People":
            areaMethod = "ABSOLUTE"
        else:
            areaMethod = "AREA_RELATED"

        radFract = peoples[i].Fraction_Radiant
        if len(str(radFract)) == 0:
            radFract = float(1 - peoples[i].Sensible_Heat_Fraction)

        for element in weekSch:
            indiceSchElement = [p for p, s in enumerate(scheduleDay) if
                                element == s.Name]
            power = round(
                float(scheduleDay[indiceSchElement[0]].Value_Until_Time_1),
                4)
        lines.insert(gainNum + 2, ' CONVECTIVE=' + str(
            power * (1 - radFract)) + ' : RADIATIVE=' + str(
            power * radFract) +
                     ' : HUMIDITY=0.066 : ELPOWERFRAC=0 : ' + areaMethod + ' : CATEGORY=PEOPLE\n')

    # Writing LIGHT gains infos to lines
    for i in range(0, len(lights)):

        lines.insert(gainNum + 1, 'GAIN LIGHT' + '_' + lights[i].Name + '\n')

        if lights[i].Design_Level_Calculation_Method == "Watts":
            areaMethod = "ABSOLUTE"
            power = round(float(lights[i].Lighting_Level), 4)
        elif lights[i].Design_Level_Calculation_Method == "Watts/Area":
            areaMethod = "AREA_RELATED"
            power = round(float(lights[i].Watts_per_Zone_Floor_Area), 4)
        else:
            areaMethod = "AREA_RELATED"
            power = 0
            log(
                "Could not find the Light Power Density, cause depend on the number of peoples (Watts/Person)",
                lg.WARNING, name="CoverterLog",
                filename="CoverterLog")

        radFract = float(lights[i].Fraction_Radiant)

        lines.insert(gainNum + 2, ' CONVECTIVE=' + str(
            power * (1 - radFract)) + ' : RADIATIVE=' + str(power * radFract) +
                     ' : HUMIDITY=0 : ELPOWERFRAC=1 : ' + areaMethod + ' : CATEGORY=LIGHTS\n')

    # Writing EQUIPMENT gains infos to lines
    for i in range(0, len(equipments)):

        lines.insert(gainNum + 1,
                     'GAIN EQUIPMENT' + '_' + equipments[i].Name + '\n')

        if equipments[i].Design_Level_Calculation_Method == "Watts":
            areaMethod = "ABSOLUTE"
            power = round(float(equipments[i].Design_Level), 4)
        elif equipments[i].Design_Level_Calculation_Method == "Watts/Area":
            areaMethod = "AREA_RELATED"
            power = round(float(equipments[i].Watts_per_Zone_Floor_Area), 4)
        else:
            areaMethod = "AREA_RELATED"
            power = 0
            log(
                "Could not find the Equipment Power Density, cause depend on the number of peoples (Watts/Person)",
                lg.WARNING, name="CoverterLog",
                filename="CoverterLog")

        radFract = float(equipments[i].Fraction_Radiant)

        lines.insert(gainNum + 2, ' CONVECTIVE=' + str(
            power * (1 - radFract)) + ' : RADIATIVE=' + str(power * radFract) +
                     ' : HUMIDITY=0 : ELPOWERFRAC=1 : ' + areaMethod + ' : CATEGORY=LIGHTS\n')
    # endregion

    # Write SCHEDULES from IDF to lines (T3D)
    # Get line number where to write
    scheduleNum = ar.checkStr(lines, 'S c h e d u l e s')

    hour_list = list(range(25))
    week_list = list(range(1, 8))
    # Write schedules DAY and WEEK in lines
    for schedule_name in schedule_names:
        for period in ['weeks', 'days']:
            for i in range(0, len(schedules[schedule_name][period])):

                lines.insert(scheduleNum + 1,
                             '!-SCHEDULE ' + schedules[schedule_name][period][
                                 i].Name + '\n')

                if period == 'days':
                    lines.insert(scheduleNum + 2,
                                 '!- HOURS= ' + " ".join(
                                     str(item) for item in hour_list) + '\n')

                    lines.insert(scheduleNum + 3,
                                 '!- VALUES= ' + " ".join(
                                     str(item) for item in
                                     schedules[schedule_name][period][
                                         i].fieldvalues[3:]) + '\n')

                if period == 'weeks':
                    lines.insert(scheduleNum + 2,
                                 '!- DAYS= ' + " ".join(
                                     str(item) for item in week_list) + '\n')

                    lines.insert(scheduleNum + 3,
                                 '!- VALUES= ' + " ".join(
                                     str(item) for item in
                                     rotate(schedules[schedule_name][period][
                                                i].fieldvalues[2:9], 1)) + '\n')

    # Write WINDOWS chosen by the user (from Berkeley lab library) in lines (T3D)
    # Get window from library
    # window = (win_id, description, design, u_win, shgc_win, t_sol_win, rf_sol,
    #                 t_vis_win, lay_win, width, window_bunches[win_id],
    #                 and maybe tolerance)
    window = choose_window(2.2, 0.64, 0.8, 0.05, window_lib)
    # If tolerance was not respected to find a window, write in log a warning
    if len(window) > 11:
        log(
            "WARNING : window tolerance was not respected. Final tolerance=  {:,.2f}".format(
                window[-1]), lg.WARNING, name="CoverterLog",
            filename="CoverterLog")
    # Write in log (info) the characteristics of the window
    log(
        "Characterisitics of the chosen window are: u_value= {:,.2f}, "
        "SHGC= {:,.2f}, t_vis= {:,.2f}".format(window[3], window[4], window[7]),
        lg.INFO, name="CoverterLog", filename="CoverterLog")

    # Get line number where to write
    windowNum = ar.checkStr(lines,
                            'W i n d o w s')
    # Write
    lines.insert(windowNum + 2,
                 '!- WINID = ' + str(window[0]) + ': HINSIDE = 11:'
                                                  ' HOUTSIDE = 64: SLOPE = -999: '
                                                  'SPACID = 4: WWID = 0.77: WHEIG = 1.08: '
                                                  'FFRAME = 0.15: UFRAME = 8.17: ABSFRAME = 0.6: '
                                                  'RISHADE = 0: RESHADE = 0: REFLISHADE = 0.5: '
                                                  'REFLOSHADE = 0.5: CCISHADE = 0.5: '
                                                  'EPSFRAME = 0.9: EPSISHADE = 0.9: '
                                                  'ITSHADECLOSE = INPUT 1 * SHADE_CLOSE: '
                                                  'ITSHADEOPEN = INPUT 1 * SHADE_OPEN: '
                                                  'FLOWTOAIRNODE = 1: PERT = 0: PENRT = 0: '
                                                  'RADMATERIAL = undefined: '
                                                  'RADMATERIAL_SHD1 = undefined')

    # Get line number to write the EXTENSION_WINPOOL
    extWinpoolNum = ar.checkStr(lines,
                                '!-_EXTENSION_WINPOOL_START_')
    count = 0
    for line in window[10]:
        lines.insert(extWinpoolNum + count, '!-' + line)
        count += 1

    # Get line number to write the Window description
    winDescriptionNum = ar.checkStr(lines,
                                    'WinID Description')
    lines.insert(winDescriptionNum + 1,
                 '!-' + str(window[0]) + ' ' + str(window[1])
                 + ' ' + str(window[2]) + ' ' + str(window[3]) + ' ' +
                 str(window[4]) + ' ' + str(window[5]) + ' ' + str(window[6]) +
                 ' ' + str(window[7]) + ' ' + str(window[8]) + ' ' + str(
                     window[9]) + '\n')

    # Save file at output_folder
    if output_folder is None:
        # User did not provide an output folder path. We use the default setting
        output_folder = ar.settings.data_folder

    if not os.path.isdir(output_folder):
        os.mkdir(output_folder)

    with open(os.path.join(output_folder, "T3D_" + list(idf_dict.keys())[0]),
              "w") as converted_file:
        for line in lines:
            converted_file.write(str(line))

    log("Write data from IDF to T3D in {:,.2f} seconds".format(
        time.time() - start_time), lg.INFO, name="CoverterLog",
        filename="CoverterLog")
