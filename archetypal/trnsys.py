import logging as lg
import os
import time
import uuid
from eppy import modeleditor

import archetypal as ar
from archetypal import log, write_lines


def clear_name_idf_objects(idfFile):
    objs = ['MATERIAL', 'MATERIAL:NOMASS', 'MATERIAL:AIRGAP', 'CONSTRUCTION',
            'FENESTRATIONSURFACE:DETAILED', 'BUILDINGSURFACE:DETAILED', 'ZONE',
            'BUILDING', 'SITE:LOCATION']
    uniqueList = []

    # For all categorie that we want to change Names
    for obj in objs:
        epObjects = idfFile.idfobjects[obj]

        # For all objects in Category
        for epObject in epObjects:
            # Do not take fenestration, to be treated later
            fenestration = [s for s in ['fenestration', 'shgc', 'window'] if
                            s in epObject.Name.lower()]
            if not fenestration:
                old_name = epObject.Name
                # clean old name by removing spaces, "-", period, "{", "}", doubleunderscore
                new_name = old_name.replace(" ", "_").replace("-", "_").replace(
                    ".", "_").replace("{", "").replace("}", "").replace("__",
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

            else:
                continue


def convert_idf_to_t3d(idf):
    """

    Args:
        idf (str): ejfufidfq

    Returns:

    """
    start_time = time.time()
    # Load IDF file(s)
    idf_file = ar.load_idf(idf)
    idf_file = idf_file[os.path.basename(idf)]
    log("IDF files loaded in {:,.2f} seconds".format(time.time() - start_time),
        lg.INFO, name="CoverterLog", filename="CoverterLog", avoid_console=True)

    # Load IDF_T3D template
    ori_idf_filename = "originBUISketchUp.idf"
    ori_idf_filepath = os.path.join("..", "tests", "input_data", "trnsys",
                                    ori_idf_filename)
    # Read IDF_T3D template and write lines in variable
    lines = open(ori_idf_filepath).readlines()

    # Create temp file path to write lines during process
    tempfile_name = os.path.basename(idf)
    tempfile_path = os.path.join(ar.settings.cache_folder, "TEMP_" + tempfile_name)

    # Clean names of idf objects (e.g. 'MATERIAL')
    start_time = time.time()
    clear_name_idf_objects(idf_file)
    log("Cleaned IDF object names in {:,.2f} seconds".format(
        time.time() - start_time), lg.INFO, name="CoverterLog",
        filename="CoverterLog")

    # Get objects from IDF file
    materials = idf_file.idfobjects['MATERIAL']
    materialNoMass = idf_file.idfobjects['MATERIAL:NOMASS']
    materialAirGap = idf_file.idfobjects['MATERIAL:AIRGAP']
    versions = idf_file.idfobjects['VERSION']
    buildings = idf_file.idfobjects['BUILDING']
    locations = idf_file.idfobjects['SITE:LOCATION']
    globGeomRules = idf_file.idfobjects['GLOBALGEOMETRYRULES']
    constructions = idf_file.idfobjects['CONSTRUCTION']
    fenestrationSurfs = idf_file.idfobjects['FENESTRATIONSURFACE:DETAILED']
    buildingSurfs = idf_file.idfobjects['BUILDINGSURFACE:DETAILED']
    zones = idf_file.idfobjects['ZONE']

    # Write data from IDF file to T3D file
    start_time = time.time()

    # Write VERSION from IDF to lines (T3D)
    # Get line number where to write
    versionNum = ar.checkStr(ori_idf_filepath,
                             'all objects in class: version')
    # Writing
    for i in range(0, len(versions)):
        lines.insert(versionNum,
                     ",".join(str(item) for item in versions.list2[i]) + ';')

    # Write lines in temp file
    write_lines(tempfile_path, lines)
    # Read temp file to update lines
    lines = open(tempfile_path).readlines()

    # Write BUILDING from IDF to lines (T3D)
    # Get line number where to write
    buildingNum = ar.checkStr(tempfile_path,
                              'all objects in class: building')
    # Writing
    for building in buildings:
        lines.insert(buildingNum, building)

    # Write lines in temp file
    write_lines(tempfile_path, lines)

    # Read temp file to update lines
    lines = open(tempfile_path).readlines()

    # Write LOCATION and GLOBALGEOMETRYRULES from IDF to lines (T3D)
    # Get line number where to write
    locationNum = ar.checkStr(tempfile_path,
                              'all objects in class: location')

    # Write GLOBALGEOMETRYRULES lines
    for globGeomRule in globGeomRules:
        # Change Geometric rules from Relative to Absolute
        coordSys = 0
        if globGeomRule.Coordinate_System == 'Relative':
            coordSys = 1
            globGeomRule.Coordinate_System = 'Absolute'

        if globGeomRule.Daylighting_Reference_Point_Coordinate_System == 'Relative':
            globGeomRule.Daylighting_Reference_Point_Coordinate_System = 'Absolute'

        if globGeomRule.Rectangular_Surface_Coordinate_System == 'Relative':
            globGeomRule.Rectangular_Surface_Coordinate_System = 'Absolute'

        lines.insert(locationNum, globGeomRule)

    # Write LOCATION lines
    for location in locations:
        lines.insert(locationNum, location)

    # Write lines in temp file
    write_lines(tempfile_path, lines)

    # Read temp file to update lines
    lines = open(tempfile_path).readlines()

    # Write VARIABLEDICTONARY (Zone, BuildingSurf, FenestrationSurf) from IDF to lines (T3D)
    # Get line number where to write
    variableDictNum = ar.checkStr(tempfile_path,
                                  'all objects in class: output:variabledictionary')
    # Writing fenestrationSurface:Detailed in lines
    for fenestrationSurf in fenestrationSurfs:
        fenestrationSurf.Construction_Name = "EXT_WINDOW1"
        lines.insert(variableDictNum + 2, fenestrationSurf)

    # Writing zones in lines
    for zone in zones:
        zone.Multiplier = 1
        # Coords of zone
        incrX = zone.X_Origin
        incrY = zone.Y_Origin
        incrZ = zone.Z_Origin

        # Writing buildingSurface: Detailed in lines
        for i in range(0, len(buildingSurfs)):
            #Change Outside Boundary Condition and Objects
            if buildingSurfs[i].Zone_Name == zone.Name:
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

                if 'ground' in buildingSurfs[
                    i].Outside_Boundary_Condition.lower():
                    buildingSurfs[
                        i].Outside_Boundary_Condition_Object = "BOUNDARY=INPUT 1*TGROUND"

                # Change coordinates from relative to absolute
                if coordSys:
                    # Change X vertex to
                    buildingSurfs[i].Vertex_1_Xcoordinate = buildingSurfs[
                                                                i].Vertex_1_Xcoordinate + incrX
                    buildingSurfs[i].Vertex_2_Xcoordinate = buildingSurfs[
                                                                i].Vertex_2_Xcoordinate + incrX
                    buildingSurfs[i].Vertex_3_Xcoordinate = buildingSurfs[
                                                                i].Vertex_3_Xcoordinate + incrX
                    buildingSurfs[i].Vertex_4_Xcoordinate = buildingSurfs[
                                                                i].Vertex_4_Xcoordinate + incrX

                    # Change Y vertex to
                    buildingSurfs[i].Vertex_1_Xcoordinate = buildingSurfs[
                                                                i].Vertex_1_Xcoordinate + incrY
                    buildingSurfs[i].Vertex_2_Xcoordinate = buildingSurfs[
                                                                i].Vertex_2_Xcoordinate + incrY
                    buildingSurfs[i].Vertex_3_Xcoordinate = buildingSurfs[
                                                                i].Vertex_3_Xcoordinate + incrY
                    buildingSurfs[i].Vertex_4_Xcoordinate = buildingSurfs[
                                                                i].Vertex_4_Xcoordinate + incrY

                    # Change Z vertex to
                    buildingSurfs[i].Vertex_1_Xcoordinate = buildingSurfs[
                                                                i].Vertex_1_Xcoordinate + incrZ
                    buildingSurfs[i].Vertex_2_Xcoordinate = buildingSurfs[
                                                                i].Vertex_2_Xcoordinate + incrZ
                    buildingSurfs[i].Vertex_3_Xcoordinate = buildingSurfs[
                                                                i].Vertex_3_Xcoordinate + incrZ
                    buildingSurfs[i].Vertex_4_Xcoordinate = buildingSurfs[
                                                                i].Vertex_4_Xcoordinate + incrZ

                lines.insert(variableDictNum + 2, buildingSurfs[i])

        lines.insert(variableDictNum + 2, zone)

    # Write lines in temp file
    write_lines(tempfile_path, lines)
    # Read temp file to update lines
    lines = open(tempfile_path).readlines()


    log("Write data from IDF to T3D in {:,.2f} seconds".format(
        time.time() - start_time), lg.INFO, name="CoverterLog",
        filename="CoverterLog")
