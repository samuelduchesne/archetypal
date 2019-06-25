################################################################################
# Module: trnsys.py
# Description: Convert EnergyPlus models to TrnBuild models
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import io
import logging as lg
import os
import re
import shutil
import subprocess
import sys
import time

import numpy as np
import pandas as pd
from geomeppy.geom.polygons import Polygon3D
from tqdm import tqdm

from archetypal import log, settings, Schedule, checkStr, \
    check_unique_name, angle, load_idf, load_idf_object_from_cache, hash_file


def convert_idf_to_trnbuild(idf_file, window_lib=None,
                            return_idf=False, return_b18=True,
                            return_t3d=False, return_dck=False,
                            output_folder=None, trnidf_exe_dir=os.path.join(
            settings.trnsys_default_folder,
            r"Building\trnsIDF\trnsidf.exe"),
                            template=settings.path_template_d18,
                            **kwargs):
    """Convert regular IDF file (EnergyPlus) to TRNBuild file (TRNSYS)

    There are three optional outputs:

    * the path to the modified IDF with the
          new names, coordinates, etc. of the IDF objects. It is an input file
          for EnergyPlus (.idf)
    * the path to the TRNBuild file (.b18)
    * the path to the TRNBuild input file (.idf)
    * the path to the TRNSYS dck file (.dck)

    Args:
        idf_file:
        window_lib (str): File path of the window library (from Berkeley Lab).
        return_idf (bool, optional): If True, also return the path to the
            modified IDF with the new names, coordinates, etc. of the IDF
            objects. It is an input file for EnergyPlus (.idf)
        return_b18 (bool, optional): If True, also return the path to the
            TRNBuild file (.b18).
        return_t3d (bool, optional): If True, also return the path to the
        return_dck (bool, optional): If True, also return the path to the TRNSYS
            dck file (.dck).
        output_folder (str, optional): location where output files will be
        trnidf_exe_dir (str): Path to *trnsidf.exe*.
        template (str): Path to d18 template file.
        kwargs (dict): keyword arguments sent to
            :func:`convert_idf_to_trnbuild()` or :func:`trnbuild_idf()` or
            :func:`choose_window`. "ordered=True" to have the name of idf
            objects in the outputfile in ascendant order. See
            :func:`trnbuild_idf` or :func:`choose_window()` for other parameter
            definition

    Returns:
        (tuple): A tuple containing:

            * return_b18 (str): the path to the TRNBuild file (.b18). Only
              provided if *return_b18* is True.
            * return_trn (str): the path to the TRNBuild input file (.idf). Only
              provided if *return_t3d* is True.
            * retrun_trn (str): the path to the TRNSYS dck file (.dck). Only
              provided if *return_dck* is True.

    Example:
        >>> # Exemple of setting kwargs to be unwrapped in the function
        >>> kwargs_dict = {'u_value': 2.5, 'shgc': 0.6, 't_vis': 0.78,
                   'tolerance': 0.05, 'ordered': True}
        >>> # Exemple how to call the function
        >>> convert_idf_to_trnbuild(idf_file=idf_file,
            window_lib=window_filepath,
            **kwargs_dict)

    """

    # Check if cache exists
    start_time = time.time()
    cache_filename = hash_file(idf_file)
    idf = load_idf_object_from_cache(idf_file, how='idf')
    if not idf:
        # Load IDF file(s)
        idf = load_idf(idf_file)
        log("IDF files loaded in {:,.2f} seconds".format(
            time.time() - start_time),
            lg.INFO)
        # Clean names of idf objects (e.g. 'MATERIAL')
        start_time = time.time()
        clear_name_idf_objects(idf)
        idf.saveas(filename=os.path.join(settings.cache_folder, cache_filename,
                                         cache_filename + '.idf'))
        # save_idf_object_to_cache(idf, idf_file, cache_filename, 'pickle')
        log("Cleaned IDF object names in {:,.2f} seconds".format(
            time.time() - start_time), lg.INFO)

    # Read IDF_T3D template and write lines in variable
    lines = io.TextIOWrapper(io.BytesIO(settings.template_BUI)).readlines()

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
    peoples = idf.idfobjects['PEOPLE']
    lights = idf.idfobjects['LIGHTS']
    equipments = idf.idfobjects['ELECTRICEQUIPMENT']

    # Get all construction EXCEPT fenestration ones
    constr_list = []
    for buildingSurf in buildingSurfs:
        constr_list.append(buildingSurf.Construction_Name)
    constr_list = list(set(constr_list))
    constr_list.sort()

    ordered = kwargs.get('ordered', False)
    if ordered:
        materials = list(reversed(materials))
        materialNoMass = list(reversed(materialNoMass))
        materialAirGap = list(reversed(materialAirGap))
        buildings = list(reversed(buildings))
        locations = list(reversed(locations))
        globGeomRules = list(reversed(globGeomRules))
        constructions = list(reversed(constructions))
        fenestrationSurfs = list(reversed(fenestrationSurfs))
        buildingSurfs = list(reversed(buildingSurfs))
        zones = list(reversed(zones))
        peoples = list(reversed(peoples))
        lights = list(reversed(lights))
        equipments = list(reversed(equipments))
        constr_list = list(reversed(constr_list))

    # region Get schedules from IDF
    start_time = time.time()
    schedule_names, schedules = _get_schedules(idf)

    log("Got yearly, weekly and daily schedules in {:,.2f} seconds".format(
        time.time() - start_time), lg.INFO)
    # endregion

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
        if len(constructions[i].fieldvalues) == 3 and \
                constructions[i].fieldvalues[
                    2] in mat_name:
            construct_low_res.append(constructions[i])

    # Remove constructions with only materials with resistance lower than
    # 0.0007 from IDF
    for construct in construct_low_res:
        idf.removeidfobject(construct)

    # Write data from IDF file to T3D file
    start_time = time.time()

    # Write VERSION from IDF to lines (T3D)
    _write_version(lines, versions)

    # Write BUILDING from IDF to lines (T3D)
    _write_building(buildings, lines)

    # Write LOCATION and GLOBALGEOMETRYRULES from IDF to lines (T3D) and
    # define if coordinate system is "Relative"
    coordSys = _write_location_geomrules(globGeomRules, lines, locations)

    # Determine if coordsSystem is "World" (all zones at (0,0,0))
    coordSys = _is_coordSys_world(coordSys, zones)

    # Change coordinates from relative to absolute for building surfaces
    if coordSys == 'Relative':
        # Add zone coordinates to X, Y, Z vectors
        for buildingSurf in buildingSurfs:
            surf_zone = buildingSurf.Zone_Name
            incrX, incrY, incrZ = zone_origin(idf.getobject("ZONE", surf_zone))
            _relative_to_absolute(buildingSurf, incrX, incrY, incrZ)

    # Adds or changes adjacent surface if needed
    _add_change_adj_surf(buildingSurfs, idf)
    buildingSurfs = idf.idfobjects["BUILDINGSURFACE:DETAILED"]

    # region Write VARIABLEDICTONARY (Zone, BuildingSurf, FenestrationSurf)
    # from IDF to lines (T3D)
    # Get line number where to write
    variableDictNum = checkStr(lines,
                               'ALL OBJECTS IN CLASS: '
                               'OUTPUT:VARIABLEDICTIONARY')

    # Get all surfaces having Outside boundary condition with the ground.
    # To be used to find the window's slopes
    n_ground = _get_ground_vertex(buildingSurfs)

    # Initialize list of window's slopes
    count_slope = 0
    win_slope_dict = {}

    # Writing zones in lines
    count_fs = 0
    _write_zone_buildingSurf_fenestrationSurf(buildingSurfs, coordSys, count_fs,
                                              count_slope, fenestrationSurfs,
                                              idf, lines, n_ground,
                                              variableDictNum, win_slope_dict,
                                              zones)
    # endregion

    # region Write CONSTRUCTION from IDF to lines (T3D)
    _write_constructions(constr_list, idf, lines, mat_name, materials)
    # endregion

    # Write CONSTRUCTION from IDF to lines, at the end of the T3D file
    _write_constructions_end(constr_list, idf, lines)

    # region Write LAYER from IDF to lines (T3D)
    _write_materials(lines, materialAirGap, materialNoMass, materials)
    # endregion

    # region Write GAINS (People, Lights, Equipment) from IDF to lines (T3D)
    _write_gains(equipments, idf, lights, lines, peoples)
    # endregion

    # region Write SCHEDULES from IDF to lines (T3D)
    _write_schedules(lines, schedule_names, schedules)
    # endregion

    # region Write WINDOWS chosen by the user (from Berkeley lab library) in
    # lines (T3D)
    # Get window from library
    # window = (win_id, description, design, u_win, shgc_win, t_sol_win, rf_sol,
    #                 t_vis_win, lay_win, width, window_bunches[win_id],
    #                 and maybe tolerance)

    win_u_value = kwargs.get('u_value', 2.2)
    win_shgc = kwargs.get('shgc', 0.64)
    win_tvis = kwargs.get('t_vis', 0.8)
    win_tolerance = kwargs.get('tolerance', 0.05)
    window = choose_window(win_u_value, win_shgc, win_tvis, win_tolerance,
                           window_lib)
    # If tolerance was not respected to find a window, write in log a warning
    if len(window) > 11:
        log(
            "Window tolerance was not respected. Final tolerance = "
            "{:,.2f}".format(
                window[-1]), lg.WARNING)
    # Write in log (info) the characteristics of the window
    log(
        "Characterisitics of the chosen window are: u_value = {:,.2f}, "
        "SHGC= {:,.2f}, t_vis= {:,.2f}".format(window[3], window[4], window[7]),
        lg.INFO)

    # Write windows in lines
    _write_window(lines, win_slope_dict, window)

    # Write window pool in lines
    _write_winPool(lines, window)
    # endregion

    # Save T3D file at output_folder
    if output_folder is None:
        # User did not provide an output folder path. We use the default setting
        output_folder = os.path.relpath(settings.data_folder)

    if not os.path.isdir(output_folder):
        os.mkdir(output_folder)

    t3d_path = os.path.join(output_folder, "T3D_" + os.path.basename(idf_file))
    with open(t3d_path, "w") as converted_file:
        for line in lines:
            converted_file.writelines(str(line))

    log("Write data from IDF to T3D in {:,.2f} seconds".format(
        time.time() - start_time), lg.INFO)

    # If asked by the user, save IDF file with modification done on the names,
    # coordinates, etc. at
    # output_folder
    new_idf_path = os.path.join(output_folder, "MODIFIED_" +
                                os.path.basename(idf_file))
    if return_idf:
        idf.saveas(filename=new_idf_path)

    # Run trnsidf to convert T3D to BUI
    dck = return_dck
    nonum = kwargs.get('nonum', False)
    N = kwargs.get('N', False)
    geo_floor = kwargs.get('geo_floor', 0.6)
    refarea = kwargs.get('refarea', False)
    volume = kwargs.get('volume', False)
    capacitance = kwargs.get('capacitance', False)
    trnbuild_idf(t3d_path, template, dck=dck, nonum=nonum, N=N,
                 geo_floor=geo_floor, refarea=refarea, volume=volume,
                 capacitance=capacitance,
                 trnidf_exe_dir=trnidf_exe_dir)

    # Prepare return arguments
    pre, ext = os.path.splitext(t3d_path)
    b18_path = pre + 'b18'
    dck_path = pre + 'dck'

    from itertools import compress
    return tuple(compress([new_idf_path, b18_path, t3d_path, dck_path],
                          [return_idf, return_b18, return_t3d, return_dck]))


def _add_change_adj_surf(buildingSurfs, idf):
    """Adds or changes adjacent surfaces if needed

    Args:
        buildingSurfs (idf_MSequence): IDF object from idf.idfobjects(). List of
            building surfaces ("BUILDINGSURFACE:DETAILED" in the IDF).
            Building surfaces to iterate over and determine if either a change on
            an adjacent surface is needed or  the creation of a new one
        idf (archetypal.idfclass.IDF): IDF object

    Returns:

    """
    adj_surfs_to_change = {}
    adj_surfs_to_make = []
    for buildingSurf in buildingSurfs:
        if 'zone' in buildingSurf.Outside_Boundary_Condition.lower():
            # Get the surface EpBunch that is adjacent to the building surface
            outside_bound_zone = \
                buildingSurf.Outside_Boundary_Condition_Object
            surfs_in_bound_zone = [surf for surf in buildingSurfs if
                                   surf.Zone_Name == outside_bound_zone]
            poly_buildingSurf = Polygon3D(buildingSurf.coords)
            n_buildingSurf = poly_buildingSurf.normal_vector
            area_build = poly_buildingSurf.area
            centroid_build = poly_buildingSurf.centroid
            # Check if buildingSurf has an adjacent surface
            for surf in surfs_in_bound_zone:
                if surf.Outside_Boundary_Condition.lower() == "outdoors":
                    poly_surf_bound = Polygon3D(surf.coords)
                    n_surf_bound = poly_surf_bound.normal_vector
                    area_bound = poly_surf_bound.area
                    centroid_bound = poly_surf_bound.centroid
                    # Check if boundary surface already exist: sum of normal
                    # vectors must be equal to 0 AND surfaces must have the
                    # same centroid AND surfaces must have the same area
                    if round(n_surf_bound.x + n_buildingSurf.x, 3) == 0 \
                            and \
                            round(n_surf_bound.y + n_buildingSurf.y, 3) == 0 \
                            and \
                            round(n_surf_bound.z + n_buildingSurf.z, 3) == 0 \
                            and \
                            round(centroid_bound.x, 3) == round(
                        centroid_build.x, 3) \
                            and \
                            round(centroid_bound.y, 3) == round(
                        centroid_build.y, 3) \
                            and \
                            round(centroid_bound.z, 3) == round(
                        centroid_build.z, 3) \
                            and \
                            round(area_bound, 3) == round(area_build, 3):
                        # If boundary surface exists, append the list of surface
                        # to change
                        if not surf.Name in adj_surfs_to_change:
                            adj_surfs_to_change[buildingSurf.Name] = surf.Name
                            break
            # If boundary surface does not exist, append the list of surface
            # to create
            if not adj_surfs_to_change:
                if not buildingSurf.Name in adj_surfs_to_make:
                    adj_surfs_to_make.append(buildingSurf.Name)
    # If adjacent surface found, check if Outside boundary
    # condition is a Zone and not "Outdoors"
    for key, value in adj_surfs_to_change.items():
        idf.getobject("BUILDINGSURFACE:DETAILED",
                      value).Outside_Boundary_Condition = "Zone"
        idf.getobject("BUILDINGSURFACE:DETAILED",
                      value).Outside_Boundary_Condition_Object = \
            idf.getobject("BUILDINGSURFACE:DETAILED",
                          key).Zone_Name
        idf.getobject("BUILDINGSURFACE:DETAILED",
                      value).Construction_Name = \
            idf.getobject("BUILDINGSURFACE:DETAILED",
                          key).Construction_Name
    # If did not find any adjacent surface
    for adj_surf_to_make in adj_surfs_to_make:
        buildSurf = idf.getobject("BUILDINGSURFACE:DETAILED",
                                  adj_surf_to_make)
        surf_type = buildSurf.Surface_Type
        if surf_type.lower() == "wall":
            surf_type_bound = "Wall"
        if surf_type.lower() == "floor":
            surf_type_bound = "Ceiling"
        if surf_type.lower() == "ceiling":
            surf_type_bound = "Floor"
        if surf_type.lower() == "roof":
            surf_type_bound = "Floor"
        # Create a new surface
        idf.newidfobject("BUILDINGSURFACE:DETAILED",
                         Name=buildSurf.Name + "_adj",
                         Surface_Type=surf_type_bound,
                         Construction_Name=buildSurf.Construction_Name,
                         Zone_Name=buildSurf.Outside_Boundary_Condition_Object,
                         Outside_Boundary_Condition="Zone",
                         Outside_Boundary_Condition_Object=buildSurf.Zone_Name,
                         Sun_Exposure="NoSun",
                         Wind_Exposure="NoWind",
                         View_Factor_to_Ground="autocalculate",
                         Number_of_Vertices=buildSurf.Number_of_Vertices,
                         Vertex_1_Xcoordinate=buildSurf.Vertex_4_Xcoordinate,
                         Vertex_1_Ycoordinate=buildSurf.Vertex_4_Ycoordinate,
                         Vertex_1_Zcoordinate=buildSurf.Vertex_4_Zcoordinate,
                         Vertex_2_Xcoordinate=buildSurf.Vertex_3_Xcoordinate,
                         Vertex_2_Ycoordinate=buildSurf.Vertex_3_Ycoordinate,
                         Vertex_2_Zcoordinate=buildSurf.Vertex_3_Zcoordinate,
                         Vertex_3_Xcoordinate=buildSurf.Vertex_2_Xcoordinate,
                         Vertex_3_Ycoordinate=buildSurf.Vertex_2_Ycoordinate,
                         Vertex_3_Zcoordinate=buildSurf.Vertex_2_Zcoordinate,
                         Vertex_4_Xcoordinate=buildSurf.Vertex_1_Xcoordinate,
                         Vertex_4_Ycoordinate=buildSurf.Vertex_1_Ycoordinate,
                         Vertex_4_Zcoordinate=buildSurf.Vertex_1_Zcoordinate)


def _get_schedules(idf):
    """Get schedules from IDF

    Args:
        idf (archetypal.idfclass.IDF): IDF object
    """
    schedule_names = []
    used_schedules = idf.get_used_schedules(yearly_only=True)
    schedules = {}
    for schedule_name in used_schedules:
        s = Schedule(schedule_name, idf,
                     start_day_of_the_week=idf.day_of_week_for_start_day)

        schedule_names.append(schedule_name)
        schedules[schedule_name] = {}
        year, weeks, days = s.to_year_week_day()
        schedules[schedule_name]['year'] = year
        schedules[schedule_name]['weeks'] = weeks
        schedules[schedule_name]['days'] = days
    return schedule_names, schedules


def clear_name_idf_objects(idfFile):
    """Clean names of IDF objects.

    Replaces variable names with a unique name, easy to refer to the original
    object. For example : if object is the n-th "Schedule Type Limit", then the
    new name will be "stl_00000n" - limits length to 10 characters

    Args:
        idfFile (archetypal.idfclass.IDF): IDF object where to clean names
    """

    uniqueList = []
    old_name_list = []

    # For all categories of objects in the IDF file
    for obj in tqdm(idfFile.idfobjects, desc='cleaning_names'):
        epObjects = idfFile.idfobjects[obj]

        # For all objects in Category
        count_name = 0
        for epObject in epObjects:
            # Do not take fenestration, to be treated later
            try:
                fenestration = [s for s in ['fenestration', 'shgc', 'window',
                                            'glazing'] if
                                s in epObject.Name.lower() or s in
                                epObject.key.lower()]
            except:
                fenestration = []
            if not fenestration:
                try:
                    old_name = epObject.Name
                    # For TRNBuild compatibility we oblige the new name to
                    # begin by a lowercase letter and the new name is max 10
                    # characters. The new name is done with the uppercase of
                    # the epObject type and an increment depending on the number
                    # of this epObject type. Making sure we
                    # have an unique new name
                    list_word_epObject_type = re.sub(r"([A-Z])", r" \1",
                                                     epObject.fieldvalues[
                                                         0]).split()
                    # Making sure new name will be max 10 characters
                    if len(list_word_epObject_type) > 4:
                        list_word_epObject_type = list_word_epObject_type[:4]

                    first_letters = ''.join(word[0].lower() for word in
                                            list_word_epObject_type)
                    end_count = '%06d' % count_name
                    new_name = first_letters + '_' + end_count

                    # Make sure new name does not already exist
                    new_name, count_name = check_unique_name(first_letters,
                                                             count_name,
                                                             new_name,
                                                             uniqueList)

                    uniqueList.append(new_name)
                    old_name_list.append(old_name)

                    # Changing the name in the IDF object
                    idfFile.rename(obj, old_name, new_name)
                except:
                    pass
            else:
                continue

    d = {"Old names": old_name_list, "New names": uniqueList}
    from tabulate import tabulate
    log_name = os.path.basename(idfFile.idfname) + "_clear_names.log"
    log_msg = "Here is the equivalence between the old names and the new " \
              "ones." + "\n\n" + tabulate(d, headers="keys")
    log(log_msg, name=log_name, level=lg.INFO)


def zone_origin(zone_object):
    """Return coordinates of a zone

    Args:
        zone_object (EpBunch): zone element in zone list.

    Returns:
        Coordinates [X, Y, Z] of the zone in a list.
    """
    return [zone_object.X_Origin, zone_object.Y_Origin, zone_object.Z_Origin]


def closest_coords(surfList, to=[0, 0, 0]):
    """Find closest coordinates to given ones

    Args:
        surfList (idf_MSequence): list of surfaces with coordinates of each one.
        to (list): list of coordinates we want to calculate the distance from.

    Returns:
        the closest point (its coordinates x, y, z) to the point chosen (input
        "to")
    """
    from scipy.spatial import cKDTree
    size = recursive_len(
        [buildingSurf.coords for buildingSurf in surfList])
    tuple_list = []
    for surf in surfList:
        for i in range(0, len(surf.coords)):
            tuple_list.append(surf.coords[i])

    nbdata = np.array(tuple_list)
    btree = cKDTree(data=nbdata, compact_nodes=True, balanced_tree=True)
    dist, idx = btree.query(np.array(to).T, k=1)
    x, y, z = nbdata[idx]
    return x, y, z


def recursive_len(item):
    """Calculate the number of elements in nested list

    Args:
        item (list): list of lists (i.e. nested list)

    Returns:
        Total number of elements in nested list
    """
    if type(item) == list:
        return sum(recursive_len(subitem) for subitem in item)
    else:
        return 1


def rotate(l, n):
    """Shift list elements to the left

    Args:
        l (list): list to rotate
        n (int): number to shift list to the left

    Returns:
        list: shifted list.
    """
    return l[n:] + l[:n]


def parse_window_lib(window_file_path):
    """Function that parse window library from Berkeley Lab in two parts. First
    part is a dataframe with the window characteristics. Second part is a
    dictionary with the description/properties of each window.

    Args:
        window_file_path (str): Path to the window library

    Returns:
        tuple: a tuple of:

            * dataframe: df_windows, a dataframe with the window characteristics
              in the columns and the window id as rows
            * dict: bunches, a dict with the window id as key and
              description/properties of each window as value
    """

    # Read window library and write lines in variable
    if window_file_path is None:
        all_lines = io.TextIOWrapper(io.BytesIO(
            settings.template_winLib)).readlines()
    else:
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
    output_folder = os.path.relpath(settings.data_folder)

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
    bunch_delimiter = 'BERKELEY LAB WINDOW v7.4.6.0  DOE-2 Data File : Multi ' \
                      'Band Calculation : generated with Trnsys18.std\n'
    detailed_windows = all_lines[0:indice_end[0]]

    # 1 window = 55 lines
    bunches_list = list(chunks(detailed_windows, 55))

    bunches = dict(get_window_id(bunches_list))

    return df_windows, bunches


def get_window_id(bunches):
    """Return bunch of window properties with their window id

    Args:
        bunches (dict): dict with the window id as key and
            description/properties of each window as value
    """
    id_line = 'Window ID   :'
    for bunch in bunches:
        for line in bunch:
            if id_line in line:
                _, value = line.split(':')
                value = int(value.strip())
                yield value, bunch


def chunks(l, n):
    """Yield successive n-sized chunks from l

    Args:
        l (list): list to divide in chunks
        n (int): number of chunks we want
    """
    for i in range(0, len(l), n):
        yield l[i:i + n]


def choose_window(u_value, shgc, t_vis, tolerance, window_lib_path):
    """Return window object from TRNBuild library

    Returns
        (tuple): A tuple of:

            * window_ID
            * window's description (label)
            * window's design (width of layers)
            * window u-value
            * window shgc
            * window solar transmittance
            * window solar refraction
            * window visible transmittance
            * number of layers of the window
            * window width
            * the "bunch" of description/properties from Berkeley lab

            If tolerance not respected return new tolerance used to find a
            window.

    Args:
        u_value (float): U_value of the glazing given by the user
        shgc (float): SHGC of the glazing given by the user
        t_vis (float): Visible transmittance of the glazing given by the user
        tolerance (float): Maximum tolerance on u_value, shgc and tvis wanted by
            the user
        window_lib_path (.dat file): window library from Berkeley lab
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
    win_id, description, design, u_win, shgc_win, t_sol_win, rf_sol_win, \
    t_vis_win, lay_win, width = \
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


def trnbuild_idf(idf_file, template=os.path.join(
    settings.trnsys_default_folder,
    r"Building\trnsIDF\NewFileTemplate.d18"), dck=False, nonum=False, N=False,
                 geo_floor=0.6, refarea=False, volume=False, capacitance=False,
                 trnidf_exe_dir=os.path.join(settings.trnsys_default_folder,
                                             r"Building\trnsIDF\trnsidf.exe")):
    """This program sorts and renumbers the IDF file and writes a B18 file based
    on the geometric information of the IDF file and the template D18 file. In
    addition, an template DCK file can be generated.

    Args:
        idf_file (str): path/filename.idf
        template (str): path/NewFileTemplate.d18
        dck (bool): If True, create a template DCK
        nonum (bool, optional): If True, no renumeration of surfaces
        N (optional): BatchJob Modus
        geo_floor (float, optional): generates GEOSURF values for distributing
            direct solar radiation where 60 % is directed to the floor, the rest
            to walls/windows. Default = 0.6
        refarea (bool, optional): If True, floor reference area of airnodes is
            updated
        volume (bool, True): If True, volume of airnodes is updated
        capacitance (bool, True): If True, capacitance of airnodes is updated
        trnidf_exe_dir (str): Path of the trnsidf.exe executable

    Returns:
        str: status

    Raises:
        CalledProcessError: When could not run command with trnsidf.exe (to
        create BUI file from IDF (T3D) file

    Example:
        >>> # Exemple of setting kwargs to be unwrapped in the function
        >>> kwargs_dict = {'dck': True, 'geo_floor': 0.57}
        >>> # Exemple how to call the function
        >>> trnbuild_idf(idf_file, template=os.path.join(
            settings.trnsys_default_folder,
            r"Building\\trnsIDF\\NewFileTemplate.d18"),
            trnidf_exe_dir=os.path.join(settings.trnsys_default_folder,
            r"Building\\trnsIDF\\trnsidf.exe"), **kwargs_dict)
        >>> INFO: Where settings.trnsys_default_folder must be defined inside
            the configuration file of the package
    """
    # first copy idf_file into output folder
    if not os.path.isdir(settings.data_folder):
        os.mkdir(settings.data_folder)
    head, tail = os.path.split(idf_file)
    new_idf_file = os.path.relpath(os.path.join(settings.data_folder, tail))
    if new_idf_file != idf_file:
        shutil.copy(idf_file, new_idf_file)
    idf_file = os.path.abspath(new_idf_file)  # back to idf_file
    del new_idf_file, head, tail

    # Continue
    args = locals().copy()
    idf = os.path.abspath(args.pop('idf_file'))
    template = os.path.abspath(args.pop('template'))
    trnsysidf_exe = os.path.abspath(args.pop('trnidf_exe_dir'))

    if not os.path.isfile(idf) or not os.path.isfile(template):
        raise FileNotFoundError()

    if sys.platform == 'win32':
        cmd = [trnsysidf_exe]
    else:
        cmd = ['wine', trnsysidf_exe]
    cmd.extend([idf])
    cmd.extend([template])
    for arg in args:
        if args[arg]:
            if isinstance(args[arg], bool):
                args[arg] = ''
            if args[arg] != "":
                cmd.extend(['/{}={}'.format(arg, args[arg])])
            else:
                cmd.extend(['/{}'.format(arg)])

    try:
        # execute the command
        log('Running cmd: {}'.format(cmd), lg.DEBUG)
        command_line_process = subprocess.Popen(cmd,
                                                stdout=subprocess.PIPE,
                                                stderr=subprocess.STDOUT)
        process_output, _ = command_line_process.communicate()
        # process_output is now a string, not a file
        log(process_output.decode('utf-8'), lg.DEBUG)
    except subprocess.CalledProcessError as exception:
        log('Exception occured: ' + str(exception), lg.ERROR)
        log('Trnsidf.exe failed', lg.ERROR)
        return False
    else:
        # Send trnsidf log to logger
        pre, ext = os.path.splitext(idf)
        log_file = pre + '.log'
        if os.path.isfile(log_file):
            with open(log_file, 'r') as f:
                log(f.read(), lg.DEBUG)

        return True


def _write_zone_buildingSurf_fenestrationSurf(buildingSurfs, coordSys, count_fs,
                                              count_slope, fenestrationSurfs,
                                              idf, lines, n_ground,
                                              variableDictNum, win_slope_dict,
                                              zones):
    """Does several actions on the zones, fenestration and building surfaces.
    Then, writes zone, fenestration and building surfaces information in lines.

    Zones:
        1. If the geometry global rule is 'World', convert zone's coordinates to
           absolute.
        2. Rounds zone's coordinates to 4 decimal.
        3. Write zones in lines (T3D file).

    Fenestration surfaces:
        1. If the geometry global rule is 'Relative', convert fenestration's
           coordinates to absolute.
        2. Find the window slope and create a new window object (to write in T3D
           file) for each different slope.
        3. Rounds fenestration surface's coordinates to 4 decimal.
        4. Write fenestration surfaces in lines (T3D file).

    Building surfaces:
        1. If the geometry global rule is 'Relative', convert building surface's
           coordinates to absolute.
        2. Determine the outside boundary condition (eg. 'ground') of each
           surface. If boundary is 'surface' or 'zone', modify the surface to
           make sure adjancency is well done between surfaces (see
           _modify_adj_surface()). If boundary is 'ground', apply ground
           temperature to the Outside_Boundary_Condition_Object. If the boundary
           is 'adiabatic', apply an IDENTICAL boundary to the
           Outside_Boundary_Condition_Object.
        3. Rounds building surface's coordinates to 4 decimal
        4. Write building surfaces in lines (T3D file)

    Args:
        buildingSurfs (idf_MSequence): IDF object from idf.idfobjects(). List of
            building surfaces ("BUILDINGSURFACE:DETAILED" in the IDF).
        coordSys (str): Coordinate system of the IDF file. Can be 'Absolute'
        count_fs (int): Count of the number of fenestration surfaces.
        count_slope (int): Count of the different window's slopes
        fenestrationSurfs (idf_MSequence): IDF object from idf.idfobjects().
            List of fenestration surfaces ("FENESTRATIONSURFACE:DETAILED" in
            the IDF).
        idf (archetypal.idfclass.IDF): IDF object
        lines (list): Text to create the T3D file (IDF file to import in
            TRNBuild). To be appended (insert) here
        n_ground (Vector 3D): Normal vector of the ground surface
        variableDictNum (int): Line number where to write the zones,
            fenestration and building surfaces
        win_slope_dict (dict): Dictionary with window's names as key and
            window's slope as value
        zones (idf_MSequence): IDF object from idf.idfobjects(). List of zones
            ("ZONES" in the IDF).
    """
    for zone in zones:
        zone.Direction_of_Relative_North = 0.0
        if zone.Multiplier == '':
            zone.Multiplier = 1
        # Coords of zone
        incrX, incrY, incrZ = zone_origin(zone)

        # Writing fenestrationSurface:Detailed in lines
        for fenestrationSurf in fenestrationSurfs:
            surfName = fenestrationSurf.Building_Surface_Name
            if idf.getobject("BUILDINGSURFACE:DETAILED",
                             surfName).Zone_Name == zone.Name:
                count_fs += 1
                # Clear fenestrationSurface:Detailed name
                fenestrationSurf.Name = 'fsd_' + '%06d' % count_fs
                # Insure right number of vertices
                fenestrationSurf.Number_of_Vertices = len(
                    fenestrationSurf.coords)

                # Change coordinates from relative to absolute
                if coordSys == 'Relative':
                    # Add zone coordinates to X, Y, Z vectors to fenestration
                    # surface
                    _relative_to_absolute(fenestrationSurf, incrX, incrY, incrZ)

                # Round vertex to 4 decimal digit max
                _round_vertex(fenestrationSurf)

                # Polygon from vector's window surface
                poly_window = Polygon3D(fenestrationSurf.coords)
                # Normal vectors of the polygon
                n_window = poly_window.normal_vector

                # Calculate the slope between window and the ground (with
                # normal vectors)
                win_slope = 180 * angle(n_ground, n_window) / np.pi
                if win_slope > 90:
                    win_slope -= 180

                # Add a construction name if slope does not already exist
                if win_slope not in win_slope_dict.values():
                    count_slope += 1
                    # Insure right construction name
                    fenestrationSurf.Construction_Name = "EXT_WINDOW{}".format(
                        count_slope)
                    # Append win_slope_dict
                    win_slope_dict[
                        fenestrationSurf.Construction_Name] = win_slope

                else:
                    fenestrationSurf.Construction_Name = \
                        [key for key in win_slope_dict.keys() if
                         win_slope == win_slope_dict[key]][0]

                lines.insert(variableDictNum + 2, fenestrationSurf)

        # Writing buildingSurface: Detailed in lines
        surfList = []
        for buildingSurf in buildingSurfs:
            # Change Outside Boundary Condition and Objects
            if buildingSurf.Zone_Name == zone.Name:
                buildingSurf.Number_of_Vertices = len(
                    buildingSurf.coords)
                surfList.append(buildingSurf)
                # Verify if surface is adjacent. If yes, modifies it
                if 'surface' in buildingSurf.Outside_Boundary_Condition.lower():
                    _modify_adj_surface(buildingSurf, idf)

                if 'ground' in buildingSurf.Outside_Boundary_Condition.lower():
                    buildingSurf.Outside_Boundary_Condition_Object = \
                        "BOUNDARY=INPUT 1*TGROUND"

                if 'adiabatic' in \
                        buildingSurf.Outside_Boundary_Condition.lower():
                    buildingSurf.Outside_Boundary_Condition = \
                        "OtherSideCoefficients"
                    buildingSurf.Outside_Boundary_Condition_Object = \
                        "BOUNDARY=IDENTICAL"

                if 'othersidecoefficients' in \
                        buildingSurf.Outside_Boundary_Condition.lower():
                    buildingSurf.Outside_Boundary_Condition = \
                        "OtherSideCoefficients"
                    buildingSurf.Outside_Boundary_Condition_Object = \
                        "BOUNDARY=INPUT 1*TBOUNDARY"

                if 'othersideconditionsmodel' in \
                        buildingSurf.Outside_Boundary_Condition.lower():
                    msg = 'Surface {"buildSurfName"} has ' \
                          '"OtherSideConditionsModel" as an outside ' \
                          'boundary condition, that is not implemented'.format(
                        buildSurfName=buildingSurf.Name)
                    raise NotImplementedError(msg)

                # Round vertex to 4 decimal digit max
                _round_vertex(buildingSurf)

                # Makes sure idf object key is not all upper string
                buildingSurf.key = "BuildingSurface:Detailed"

                lines.insert(variableDictNum + 2, buildingSurf)

        # Change coordinates from world (all zones to 0) to absolute
        if coordSys == 'World':
            zone.X_Origin, zone.Y_Origin, zone.Z_Origin = closest_coords(
                surfList, to=zone_origin(zone))

        # Round vertex to 4 decimal digit max
        zone.X_Origin = round(zone.X_Origin, 4)
        zone.Y_Origin = round(zone.Y_Origin, 4)
        zone.Z_Origin = round(zone.Z_Origin, 4)

        lines.insert(variableDictNum + 2, zone)


def _modify_adj_surface(buildingSurf, idf):
    """If necessary, modify outside boundary conditions and vertices of the
    adjacent building surface

    Args:
        buildingSurf (EpBunch): Building surface object to modify
        idf (archetypal.idfclass.IDF): IDF object
    """
    # Force outside boundary condition to "Zone"
    buildingSurf.Outside_Boundary_Condition = "Zone"
    # Get the surface EpBunch that is adjacent to the building surface
    outside_bound_surf = buildingSurf.Outside_Boundary_Condition_Object
    # If outside_bound_surf is the same surface as buildingSurf, raises error
    if outside_bound_surf == buildingSurf.Name:
        msg = 'The IDF file "{idfname}" could not be converted. The problem ' \
              'comes from adjacent surfaces that have themselves as an ' \
              'Outside Boundary Condition Object. For example, surf_1 has ' \
              '"Surface" as Outside Boundary Condition, but the Outside ' \
              'Boundary Condition Object is surf_1 too. This comes from the ' \
              'EnergyPlus IDF. Here it is surface ' \
              '"{surfname}" that have "{outside_bound}" as Outside ' \
              'Boundary Condition Object.'.format(
            idfname=os.path.basename(
            idf.idfname), surfname=buildingSurf.Name, outside_bound=outside_bound_surf)
        raise NotImplementedError(msg)
    else:
        # Replace the Outside_Boundary_Condition_Object that was the
        # outside_bound_surf, by the adjacent zone name
        buildingSurf.Outside_Boundary_Condition_Object = idf.getobject(
            'ZONE', idf.getobject('BUILDINGSURFACE:DETAILED',
                                  outside_bound_surf).Zone_Name).Name
        # Force same construction for adjacent surfaces
        buildingSurf.Construction_Name = idf.getobject(
            'BUILDINGSURFACE:DETAILED',
            outside_bound_surf).Construction_Name
        # Polygon from vector's adjacent surfaces
        poly1 = Polygon3D(buildingSurf.coords)
        poly2 = Polygon3D(idf.getobject('BUILDINGSURFACE:DETAILED',
                                        outside_bound_surf).coords)
        # Normal vectors of each polygon
        n1 = poly1.normal_vector
        n2 = poly2.normal_vector
        # Verify if normal vectors of adjacent surfaces have
        # opposite directions
        if round((n1 + n2).x, 2) != 0 or round((n1 + n2).y,
                                               2) != 0 or round(
            (n1 + n2).z, 2) != 0:
            # If not, inverse vertice of buildingSurf
            # (Vertex4 become Vertex1, Vertex2 become Vertex3, etc.)
            _inverse_vertices_surf(buildingSurf, idf, outside_bound_surf,
                                   'BUILDINGSURFACE:DETAILED')

    a = idf.getobject(
    'BUILDINGSURFACE:DETAILED',
    outside_bound_surf)
    b=1


def _inverse_vertices_surf(buildingSurf, idf, outside_bound_surf,
                           idfobject_key):
    """Inverses the vertices of a surface (last vertex becomes the first one,
    etc.)

    Args:
        buildingSurf (EpBunch): Building surface object to modify
        idf (archetypal.idfclass.IDF): IDF object
        outside_bound_surf (str): Name of the adjacent surface to the
            buildingSurf
        idfobject_key (str): Section name of the IDF where to find the
            outside_bound_surf
    """
    for j, k in zip(range(1, len(
            buildingSurf.coords) + 1), range(
        len(buildingSurf.coords), 0, -1)):
        idf.getobject(idfobject_key,
                      outside_bound_surf)[
            "Vertex_" + str(j) + "_Xcoordinate"] \
            = buildingSurf[
            "Vertex_" + str(k) + "_Xcoordinate"]
        idf.getobject(idfobject_key,
                      outside_bound_surf)[
            "Vertex_" + str(j) + "_Ycoordinate"] \
            = buildingSurf[
            "Vertex_" + str(k) + "_Ycoordinate"]
        idf.getobject(idfobject_key,
                      outside_bound_surf)[
            "Vertex_" + str(j) + "_Zcoordinate"] \
            = buildingSurf[
            "Vertex_" + str(k) + "_Zcoordinate"]


def _round_vertex(surface, nbr_decimal=4):
    """Round vertex to the number of decimal (nbr_decimal) wanted

    Args:
        surface (EpBunch): Surface object to which we want to round its vertices
        nbr_decimal (int): Number of decimal to round
    """
    for j in range(1, len(
            surface.coords) + 1):
        surface["Vertex_" + str(j) + "_Xcoordinate"] \
            = \
            round(surface[
                      "Vertex_" + str(j) + "_Xcoordinate"], nbr_decimal)
        surface["Vertex_" + str(j) + "_Ycoordinate"] \
            = \
            round(surface[
                      "Vertex_" + str(j) + "_Ycoordinate"], nbr_decimal)
        surface["Vertex_" + str(j) + "_Zcoordinate"] \
            = \
            round(surface[
                      "Vertex_" + str(j) + "_Zcoordinate"], nbr_decimal)


def _relative_to_absolute(surface, incrX, incrY, incrZ):
    """Convert relative coordinates to absolute ones

    Args:
        surface (EpBunch): Surface object to which we want to convert its
            vertices
        incrX (str): X coordinate of the surface's zone
        incrY (str): Y coordinate of the surface's zone
        incrZ (str): Z coordinate of the surface's zone
    """
    for j in range(1, len(
            surface.coords) + 1):
        surface["Vertex_" + str(j) + "_Xcoordinate"] \
            = \
            surface[
                "Vertex_" + str(j) + "_Xcoordinate"] + incrX
        surface["Vertex_" + str(j) + "_Ycoordinate"] \
            = \
            surface[
                "Vertex_" + str(j) + "_Ycoordinate"] + incrY
        surface["Vertex_" + str(j) + "_Zcoordinate"] \
            = \
            surface[
                "Vertex_" + str(j) + "_Zcoordinate"] + incrZ


def _write_winPool(lines, window):
    """Write the window pool (from Berkeley Lab window library) in lines

    Args:
        lines (list): Text to create the T3D file (IDF file to import in
            TRNBuild). To be appended (insert) here
        window (tuple): Information to write in the window pool extension (
    """
    # Get line number to write the EXTENSION_WINPOOL
    extWinpoolNum = checkStr(lines,
                             '!-_EXTENSION_WINPOOL_START_')
    count = 0
    for line in window[10]:
        lines.insert(extWinpoolNum + count, '!-' + line)
        count += 1
    # Get line number to write the Window description
    winDescriptionNum = checkStr(lines,
                                 'WinID Description')
    lines.insert(winDescriptionNum + 1,
                 '!-' + str(window[0]) + ' ' + str(window[1])
                 + ' ' + str(window[2]) + ' ' + str(window[3]) + ' ' +
                 str(window[4]) + ' ' + str(window[5]) + ' ' + str(window[6]) +
                 ' ' + str(window[7]) + ' ' + str(window[8]) + ' ' + str(
                     window[9]) + '\n')


def _write_window(lines, win_slope_dict, window):
    """Write window information in lines

    Args:
        lines (list): Text to create the T3D file (IDF file to import in
            TRNBuild). To be appended (insert) here
        win_slope_dict (dict): Dictionary with window's names as key and
            window's slope as value
        window (tuple): Information to write in the window pool extension (
    """
    # Get line number where to write
    windowNum = checkStr(lines,
                         'W i n d o w s')
    # Write
    for key in win_slope_dict.keys():
        lines.insert(windowNum + 1, "WINDOW " + str(key) + '\n')
        lines.insert(windowNum + 2,
                     '!- WINID = ' + str(window[0]) +
                     ': HINSIDE = 11:'
                     ' HOUTSIDE = 64: SLOPE '
                     '= ' + str(win_slope_dict[key]) +
                     ': '
                     'SPACID = 4: WWID = 0.77: '
                     'WHEIG = 1.08: '
                     'FFRAME = 0.15: UFRAME = '
                     '8.17: ABSFRAME = 0.6: '
                     'RISHADE = 0: RESHADE = 0: '
                     'REFLISHADE = 0.5: '
                     'REFLOSHADE = 0.5: CCISHADE '
                     '= 0.5: '
                     'EPSFRAME = 0.9: EPSISHADE '
                     '= 0.9: '
                     'ITSHADECLOSE = INPUT 1 * '
                     'SHADE_CLOSE: '
                     'ITSHADEOPEN = INPUT 1 * '
                     'SHADE_OPEN: '
                     'FLOWTOAIRNODE = 1: PERT = '
                     '0: PENRT = 0: '
                     'RADMATERIAL = undefined: '
                     'RADMATERIAL_SHD1 = '
                     'undefined' + '\n')


def _write_schedules(lines, schedule_names, schedules):
    """Write schedules information in lines

    Args:
        lines (list): Text to create the T3D file (IDF file to import in
            TRNBuild). To be appended (insert) here
        schedule_names (list): Names of all the schedules to be written in lines
        schedules (dict): Dictionary with the schedule names as key and with
    """
    # Get line number where to write
    scheduleNum = checkStr(lines, 'S c h e d u l e s')
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


def _write_gains(equipments, idf, lights, lines, peoples):
    """Write gains in lines

    Args:
        equipments (idf_MSequence): IDF object from idf.idfobjects(). List of
            equipments ("ELECTRICEQUIPMENT" in the IDF).
        idf (archetypal.idfclass.IDF): IDF object
        lights (idf_MSequence): IDF object from idf.idfobjects(). List of
            lights ("LIGHTS" in the IDF).
        lines (list): Text to create the T3D file (IDF file to import in
            TRNBuild). To be appended (insert) here
        peoples (idf_MSequence): IDF object from idf.idfobjects()
    """
    # Get line number where to write
    gainNum = checkStr(lines, 'G a i n s')
    # Writing PEOPLE gains infos to lines
    _write_people_gain(gainNum, idf, lines, peoples)
    # Writing LIGHT gains infos to lines
    _write_light_gain(gainNum, lights, lines)
    # Writing EQUIPMENT gains infos to lines
    _write_equipment_gain(equipments, gainNum, lines)


def _write_equipment_gain(equipments, gainNum, lines):
    """Write equipment gains in lines

    Args:
        equipments (idf_MSequence): IDF object from idf.idfobjects(). List of
            equipments ("ELECTRICEQUIPMENT" in the IDF).
        gainNum (int): Line number where to write the equipment gains
        lines (list): Text to create the T3D file (IDF file to import in
            TRNBuild). To be appended (insert) here
    """
    for i in range(0, len(equipments)):
        # Determine if gain is absolute or relative and write it into lines
        if equipments[i].Design_Level_Calculation_Method == "EquipmentLevel":
            areaMethod = "ABSOLUTE"
            try:
                power = round(float(equipments[i].Design_Level), 4)
            except Exception:
                log(
                    "Could not find the Light Power Density in the IDF file",
                    lg.WARNING)
                continue
        elif equipments[i].Design_Level_Calculation_Method == "Watts/Area":
            areaMethod = "AREA_RELATED"
            try:
                power = round(float(equipments[i].Watts_per_Zone_Floor_Area), 4)
            except Exception:
                log(
                    "Could not find the Light Power Density in the IDF file",
                    lg.WARNING)
                continue
        else:
            log(
                "Could not find the Equipment Power Density, cause depend on "
                "the number of peoples (Watts/Person)",
                lg.WARNING)
            continue

        # Find the radiant fractions
        radFract = equipments[i].Fraction_Radiant
        if len(str(radFract)) == 0:
            # Find the radiant fractions
            try:
                radFract = float(1 - equipments[i].Sensible_Heat_Fraction)
            except Exception:
                radFract = 0.42
        else:
            radFract = float(radFract)

        # Write gain from equipment in lines
        lines.insert(gainNum + 1,
                     'GAIN EQUIPMENT' + '_' + equipments[i].Name + '\n')
        lines.insert(gainNum + 2, ' CONVECTIVE=' + \
                     str(round(power * (1 - radFract), 3)) + ' : RADIATIVE=' + \
                     str(round(power * radFract, 3)) + \
                     ' : HUMIDITY=0 : ELPOWERFRAC=1 : ' + \
                     areaMethod + ' : CATEGORY=LIGHTS\n')


def _write_light_gain(gainNum, lights, lines):
    """Write gain from lights in lines

    Args:
        gainNum (int): Line number where to write the equipment gains
        lights (idf_MSequence): IDF object from idf.idfobjects(). List of
            lights ("LIGHTS" in the IDF).
        lines (list): Text to create the T3D file (IDF file to import in
            TRNBuild). To be appended (insert) here
    """
    for i in range(0, len(lights)):
        # Determine if gain is absolute or relative and write it into lines
        if lights[i].Design_Level_Calculation_Method == "LightingLevel":
            areaMethod = "ABSOLUTE"
            try:
                power = round(float(lights[i].Lighting_Level), 4)
            except Exception:
                log(
                    "Could not find the Light Power Density in the IDF file",
                    lg.WARNING)
                continue
        elif lights[i].Design_Level_Calculation_Method == "Watts/Area":
            areaMethod = "AREA_RELATED"
            try:
                power = round(float(lights[i].Watts_per_Zone_Floor_Area), 4)
            except Exception:
                log(
                    "Could not find the Light Power Density in the IDF file",
                    lg.WARNING)
                continue
        else:
            log(
                "Could not find the Light Power Density, cause depend on the "
                "number of peoples (Watts/Person)",
                lg.WARNING)
            continue

        # Find the radiant fractions
        radFract = lights[i].Fraction_Radiant
        if len(str(radFract)) == 0:
            # Find the radiant fractions
            try:
                radFract = float(1 - lights[i].Sensible_Heat_Fraction)
            except Exception:
                radFract = 0.42
        else:
            radFract = float(radFract)

        # Write gain from light in lines
        lines.insert(gainNum + 1,
                     'GAIN LIGHT' + '_' + lights[i].Name + '\n')
        lines.insert(gainNum + 2, ' CONVECTIVE=' + str(
            round(power * (1 - radFract), 3)) + ' : RADIATIVE=' + str(
            round(power * radFract, 3)) + ' : HUMIDITY=0 : ELPOWERFRAC=1 : '
                     + areaMethod + ' : CATEGORY=LIGHTS\n')


def _write_people_gain(gainNum, idf, lines, peoples):
    """
    Args:
        gainNum (int): Line number where to write the equipment gains
        idf (archetypal.idfclass.IDF): IDF object
        lines (list): Text to create the T3D file (IDF file to import in
            TRNBuild). To be appended (insert) here
        peoples (idf_MSequence): IDF object from idf.idfobjects()
    """
    for i in range(0, len(peoples)):
        # Write gain name in lines
        lines.insert(gainNum + 1,
                     'GAIN PEOPLE' + '_' + peoples[i].Name + '\n')
        # Determine if gain is absolute or relative and write it into lines
        if peoples[i].Number_of_People_Calculation_Method == "People":
            areaMethod = "ABSOLUTE"
        else:
            areaMethod = "AREA_RELATED"
        # Find the radiant fractions
        radFract = peoples[i].Fraction_Radiant
        if len(str(radFract)) == 0:
            # Find the radiant fractions
            try:
                radFract = float(1 - peoples[i].Sensible_Heat_Fraction)
            except Exception:
                radFract = 0.3
        else:
            radFract = float(radFract)

        # Find the the total power of the people gain
        power = Schedule(sch_name=peoples[i].Activity_Level_Schedule_Name,
                         idf=idf).max
        # Write gain characteristics into lines
        lines.insert(gainNum + 2, ' CONVECTIVE=' + str(
            round(power * (1 - radFract), 3)) + ' : RADIATIVE=' + str(
            round(power * radFract, 3)) + ' : HUMIDITY=0.066 : ELPOWERFRAC=0 '
                                          ': ' + areaMethod + ' : '
                                                              'CATEGORY=PEOPLE\n')


def _write_materials(lines, materialAirGap, materialNoMass, materials):
    """Write materials (LAYER in TRNBuild) in lines

    Args:
        lines (list): Text to create the T3D file (IDF file to import in
            TRNBuild). To be appended (insert) here
        materialAirGap (idf_MSequence): IDF object from idf.idfobjects(). List of
            air gap materials ("MATERIAL:AIRGAP" in the IDF).
        materialNoMass (idf_MSequence): IDF object from idf.idfobjects(). List of
            material no mass ("MATERIAL:NOMASS" in the IDF)
        materials (idf_MSequence): IDF object from idf.idfobjects(). List of
            materials ("MATERIAL" in the IDF)
    """
    # Get line number where to write
    layerNum = checkStr(lines, 'L a y e r s')
    listLayerName = []
    # Writing MATERIAL infos to lines
    _write_material(layerNum, lines, listLayerName, materials)
    # Writing MATERIAL:NOMASS infos to lines
    _write_material_nomass(layerNum, lines, listLayerName, materialNoMass)
    # Writing MATERIAL:AIRGAP infos to lines
    _write_material_airgap(layerNum, lines, listLayerName, materialAirGap)


def _write_material_airgap(layerNum, lines, listLayerName, materialAirGap):
    """
    Args:
        layerNum (int): Line number where to write the material
        lines (list): Text to create the T3D file (IDF file to import in
            TRNBuild). To be appended (insert) here
        listLayerName (list): list of material's names. To be appended when
        materialAirGap materialAirGap (idf_MSequence): IDF object from idf.idfobjects(). List of
            air gap materials ("MATERIAL:AIRGAP" in the IDF).
    """
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


def _write_material_nomass(layerNum, lines, listLayerName, materialNoMass):
    """
    Args:
        layerNum (int): Line number where to write the material
        lines (list): Text to create the T3D file (IDF file to import in
            TRNBuild). To be appended (insert) here
        listLayerName (list): list of material's names. To be appended when
        materialNoMass (idf_MSequence): IDF object from idf.idfobjects(). List of
            material no mass ("MATERIAL:NOMASS" in the IDF)
    """
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


def _write_material(layerNum, lines, listLayerName, materials):
    """
    Args:
        layerNum (int): Line number where to write the material
        lines (list): Text to create the T3D file (IDF file to import in
            TRNBuild). To be appended (insert) here
        listLayerName (list): list of material's names. To be appended when
        materials (idf_MSequence): IDF object from idf.idfobjects(). List of
            materials ("MATERIAL" in the IDF)
    """
    for i in range(0, len(materials)):
        lines.insert(layerNum + 1, '!-LAYER ' + materials[i].Name + '\n')
        listLayerName.append(materials[i].Name)

        lines.insert(layerNum + 2, '!- CONDUCTIVITY=' + str(
            round(materials[i].Conductivity * 3.6, 4)) +
                     ' : CAPACITY= ' + str(
            round(materials[i].Specific_Heat / 1000, 4)) + ' : DENSITY= ' +
                     str(round(materials[i].Density,
                               4)) + ' : PERT= 0 : PENRT= 0\n')


def _write_constructions_end(constr_list, idf, lines):
    """Write constructions at the end of lines (IDF format)

    Args:
        constr_list (list): list of construction names to be written
        idf (archetypal.idfclass.IDF): IDF object
        lines (list): Text to create the T3D file (IDF file to import in
            TRNBuild). To be appended (insert) here
    """
    # Get line number where to write
    constructionEndNum = checkStr(lines,
                                  'ALL OBJECTS IN CLASS: CONSTRUCTION')
    # Writing CONSTRUCTION infos to lines
    for constr in constr_list:
        construction = idf.getobject("CONSTRUCTION", constr)
        lines.insert(constructionEndNum, construction)


def _write_constructions(constr_list, idf, lines, mat_name, materials):
    """Write constructions in lines (TRNBuild format)

    Args:
        constr_list (list): list of construction names to be written
        idf (archetypal.idfclass.IDF): IDF object
        lines (list): Text to create the T3D file (IDF file to import in
            TRNBuild). To be appended (insert) here
        mat_name (list): list of material names to be written
        materials (idf_MSequence): IDF object from idf.idfobjects(). List of
            materials ("MATERIAL" in the IDF)
    """
    # Get line number where to write
    constructionNum = checkStr(lines, 'C O N S T R U C T I O N')
    # Writing CONSTRUCTION in lines
    for constr in constr_list:
        construction = idf.getobject("CONSTRUCTION", constr)
        lines.insert(constructionNum + 1,
                     '!-CONSTRUCTION ' + construction.Name + '\n')

        # Create lists to append with layers and thickness of construction
        layerList = []
        thickList = []

        for j in range(2, len(construction.fieldvalues)):

            if construction.fieldvalues[j] not in mat_name:

                indiceMat = [k for k, s in enumerate(materials) if
                             construction.fieldvalues[j] == s.Name]

                if not indiceMat:
                    thickList.append(0.0)
                else:
                    thickList.append(
                        round(materials[indiceMat[0]].Thickness, 4))

                layerList.append(construction.fieldvalues[j])

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
                    s in construction.fieldvalues[1].lower()]
        if not basement:
            lines.insert(constructionNum + 6,
                         '!- HFRONT   = 11 : HBACK= 64\n')
        else:
            lines.insert(constructionNum + 6,
                         '!- HFRONT   = 11 : HBACK= 0\n')


def _get_ground_vertex(buildingSurfs):
    """Find the normal vertex of ground surface

    Args:
        buildingSurfs (idf_MSequence): IDF object from idf.idfobjects(). List of
            building surfaces ("BUILDINGSURFACE:DETAILED" in the IDF).
    """
    ground_surfs = [buildingSurf for buildingSurf in buildingSurfs if
                    buildingSurf.Outside_Boundary_Condition.lower() == 'ground']
    if ground_surfs:
        ground = ground_surfs[0].coords
    else:
        ground = [(45, 28, 0), (45, 4, 0), (4, 4, 0), (4, 28, 0)]
    # Polygon from vector's ground surface
    poly_ground = Polygon3D(ground)
    # Normal vectors of the polygon
    n_ground = poly_ground.normal_vector
    return n_ground


def _is_coordSys_world(coordSys, zones):
    """
    Args:
        coordSys (str): If already assigned ('Relative' or 'Absolute),
            function returns the value
        zones (idf_MSequence): IDF object from idf.idfobjects(). List of zones
            ("ZONES" in the IDF). Zones object to iterate over, to determine
            if the coordinate system is 'World'
    """
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
    if X_zones == Y_zones and X_zones == Z_zones and Y_zones == Z_zones and \
            X_zones[0] == 0 and Y_zones[0] == 0 and Z_zones[0] == 0:
        coordSys = "World"
    return coordSys


def _write_location_geomrules(globGeomRules, lines, locations):
    """
    Args:
        globGeomRules (idf_MSequence): IDF object from idf.idfobjects(). List of
            global geometry rules ("GLOBALGEOMETRYRULES" in the IDF).
            Normally there should be only one global geometry rules.
        lines (list): Text to create the T3D file (IDF file to import in
            TRNBuild). To be appended (insert) here
        locations (idf_MSequence): IDF object from idf.idfobjects(). List of
            the building locations ("SITE:LOCATION" in the IDF). Normally
            there
            should be only one location.
    """
    # Get line number where to write
    locationNum = checkStr(lines,
                           'ALL OBJECTS IN CLASS: LOCATION')
    # Writing GLOBALGEOMETRYRULES infos to lines
    for globGeomRule in globGeomRules:
        # Change Geometric rules from Relative to Absolute
        coordSys = "Absolute"
        if globGeomRule.Coordinate_System == 'Relative':
            coordSys = "Relative"
            globGeomRule.Coordinate_System = 'Absolute'

        if globGeomRule.Daylighting_Reference_Point_Coordinate_System == \
                'Relative':
            globGeomRule.Daylighting_Reference_Point_Coordinate_System = \
                'Absolute'

        if globGeomRule.Rectangular_Surface_Coordinate_System == 'Relative':
            globGeomRule.Rectangular_Surface_Coordinate_System = 'Absolute'

        lines.insert(locationNum, globGeomRule)
    # Writing LOCATION infos to lines
    for location in locations:
        lines.insert(locationNum, location)
    return coordSys


def _write_building(buildings, lines):
    """
    Args:
        buildings (idf_MSequence): IDF object from idf.idfobjects()
        lines (list): Text to create the T3D file (IDF file to import in
            TRNBuild). To be appended (insert) here
    """
    # Get line number where to write
    buildingNum = checkStr(lines,
                           'ALL OBJECTS IN CLASS: BUILDING')
    # Writing BUILDING infos to lines
    for building in buildings:
        lines.insert(buildingNum, building)


def _write_version(lines, versions):
    """
    Args:
        lines (list): Text to create the T3D file (IDF file to import in
            TRNBuild). To be appended (insert) here
        versions (idf_MSequence): IDF object from idf.idfobjects(). List of
            the IDF file versions ("VERSION" in the IDF).
            Normally there should be only one version.
    """
    # Get line number where to write
    versionNum = checkStr(lines,
                          'ALL OBJECTS IN CLASS: VERSION')
    # Writing VERSION infos to lines
    for i in range(0, len(versions)):
        lines.insert(versionNum,
                     ",".join(str(item) for item in versions[i].fieldvalues)
                     + ';' + '\n')
