import logging as lg
import numpy as np
import os
import time
import uuid
from eppy import modeleditor
from collections import OrderedDict

import archetypal as ar
from archetypal import log, write_lines


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
            'SCHEDULE:DAY:INTERVAL', 'PEOPLE', 'LIGHTS', 'ELECTRICEQUIPMENT']
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

def zone_origin(zone_object):
    """ Return coordinates of a zone

    Args:
        zone_object (EpBunch): zone element in zone list

    Returns: Coordinates [X, Y, Z] of the zone in a list

    """
    return [zone_object.X_Origin, zone_object.Y_Origin, zone_object.Z_Origin]

def closest_coords(surfList, to=[0,0,0]):
    """Find closest coordinates to given ones

    Args:
        surfList (idf_MSequence): list of surface with coordinates of each one
        to (list): list of coordinates we want to calculate the distance from

    Returns: the closest point (its coordinates x, y, z) to the point chosen
        (input "to")

    """
    from scipy.spatial import cKDTree
    nbdata = np.array([buildingSurf.coords for buildingSurf in surfList]).reshape(len(surfList)*4,len(to))
    btree = cKDTree(data=nbdata, compact_nodes=True, balanced_tree=True)
    dist, idx = btree.query(np.array(to).T, k=1)
    x, y, z = nbdata[idx]
    return x, y, z

def convert_idf_to_t3d(idf, output_folder=None):
    """ Convert IDF file to T3D file to be able to load it in TRNBuild

    Args:
        idf (str): File path of IDF file to convert to T3D
        output_folder (str): location where output file will be saved. If None,
            saves to settings.data_folder

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
    scheduleYear = idf_file.idfobjects['SCHEDULE:YEAR']
    scheduleWeek = idf_file.idfobjects['SCHEDULE:WEEK:DAILY']
    scheduleDay = idf_file.idfobjects['SCHEDULE:DAY:INTERVAL']
    people = idf_file.idfobjects['PEOPLE']
    light = idf_file.idfobjects['LIGHTS']
    equipment = idf_file.idfobjects['ELECTRICEQUIPMENT']

    # Write data from IDF file to T3D file
    start_time = time.time()

    # Write VERSION from IDF to lines (T3D)
    # Get line number where to write
    with open(ori_idf_filepath) as ori:
        versionNum = ar.checkStr(ori,
                                 'ALL OBJECTS IN CLASS: VERSION')
    # Writing
    for i in range(0, len(versions)):
        lines.insert(versionNum,
                     ",".join(str(item) for item in versions.list2[i]) + ';')

    # Write BUILDING from IDF to lines (T3D)
    # Get line number where to write
    buildingNum = ar.checkStr(lines,
                              'ALL OBJECTS IN CLASS: BUILDING')
    # Writing
    for building in buildings:
        lines.insert(buildingNum, building)

    # Write LOCATION and GLOBALGEOMETRYRULES from IDF to lines (T3D)
    # Get line number where to write
    locationNum = ar.checkStr(lines,
                              'ALL OBJECTS IN CLASS: LOCATION')

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

    # Write VARIABLEDICTONARY (Zone, BuildingSurf, FenestrationSurf) from IDF to lines (T3D)
    # Get line number where to write
    variableDictNum = ar.checkStr(lines,
                                  'ALL OBJECTS IN CLASS: OUTPUT:VARIABLEDICTIONARY')
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
            # Change Outside Boundary Condition and Objects
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

    # Write CONSTRUCTION from IDF to lines (T3D)
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

        # Create lists to append with layers and thickness of contruction
        layerList = []
        thickList = []

        for j in range(2, len(constructions.list2[i])):

            indiceMat = [k for k, s in enumerate(materials) if
                         constructions.list2[i][j] == s.Name]
            if not indiceMat:
                thickList.append(0.0)
            else:
                thickList.append(materials[indiceMat[0]].Thickness)

            layerList.append(constructions.list2[i][j])

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

    # Write CONSTRUCTION (END) from IDF to lines (T3D)
    # Get line number where to write
    constructionEndNum = ar.checkStr(lines,
                                     'ALL OBJECTS IN CLASS: CONSTRUCTION')

    # Writing CONSTRUCTION in lines
    for i in range(0, len(constructions)):

        # Except fenestration construction
        fenestration = [s for s in ['fenestration', 'shgc', 'window'] if
                        s in constructions.list2[i][1].lower()]
        if not fenestration:
            lines.insert(constructionEndNum, constructions[i])
        else:
            continue

    # Write LAYER from IDF to lines (T3D)
    # Get line number where to write
    layerNum = ar.checkStr(lines, 'L a y e r s')

    # Write MATERIAL to lines
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

    # Write MATERIAL:NOMASS to lines
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

    # Write MATERIAL:AIRGAP to lines
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

    # Write GAINS (People, Lights, Equipment) from IDF to lines (T3D)
    # Get line number where to write
    gainNum = ar.checkStr(lines, 'G a i n s')

    # Write PEOPLE gains in lines
    for i in range(0, len(people)):

        schYearName = people[i].Activity_Level_Schedule_Name
        indiceSchYear = [k for k, s in enumerate(scheduleYear) if
                         people[i].Activity_Level_Schedule_Name == s.Name]
        schWeekName = scheduleYear[indiceSchYear[0]].ScheduleWeek_Name_1
        indiceSchWeek = [k for k, s in enumerate(scheduleWeek) if scheduleYear[
            indiceSchYear[0]].ScheduleWeek_Name_1 == s.Name]
        weekSch = list(
            OrderedDict.fromkeys(scheduleWeek.list2[indiceSchWeek[0]][2::]))

        for element in weekSch:
            lines.insert(gainNum + 1, 'GAIN PEOPLE' + '_' + element.replace(" ",
                                                                            "_").replace(
                "-", "_").replace(".", "_").replace("{", "").replace("}",
                                                                     "") + '\n')

            if people[i].Number_of_People_Calculation_Method == "People":
                areaMethod = "ABSOLUTE"
            else:
                areaMethod = "AREA_RELATED"

            radFract = people[i].Fraction_Radiant
            if len(str(radFract)) == 0:
                radFract = 1 - people[i].Sensible_Heat_Fraction

            indiceSchElement = [p for p, s in enumerate(scheduleDay) if
                                element == s.Name]
            power = round(scheduleDay[indiceSchElement[0]].Value_Until_Time_1,
                          4)
            lines.insert(gainNum + 2, ' CONVECTIVE=' + str(
                power * (1 - radFract)) + ' : RADIATIVE=' + str(
                power * radFract) +
                         ' : HUMIDITY=0.066 : ELPOWERFRAC=0 : ' + areaMethod + ' : CATEGORY=PEOPLE\n')

    # Write LIGHT gains in lines
    for i in range(0, len(light)):

        lines.insert(gainNum + 1,
                     'GAIN LIGHT' + '_' + light[i].Schedule_Name.replace(" ",
                                                                         "_").replace(
                         "-", "_").replace(".", "_").replace("{", "").replace(
                         "}", "") + '\n')

        if light[i].Design_Level_Calculation_Method == "Watts":
            areaMethod = "ABSOLUTE"
            power = round(light[i].Lighting_Level, 4)
        elif light[i].Design_Level_Calculation_Method == "Watts/Area":
            areaMethod = "AREA_RELATED"
            power = round(light[i].Watts_per_Zone_Floor_Area, 4)
        else:
            areaMethod = "AREA_RELATED"
            power = 0
            log(
                "Could not find the Light Power Density, cause depend on the number of people (Watts/Person)",
                lg.WARNING, name="CoverterLog",
                filename="CoverterLog")

        radFract = light[i].Fraction_Radiant

        lines.insert(gainNum + 2, ' CONVECTIVE=' + str(
            power * (1 - radFract)) + ' : RADIATIVE=' + str(power * radFract) +
                     ' : HUMIDITY=0 : ELPOWERFRAC=1 : ' + areaMethod + ' : CATEGORY=LIGHTS\n')

    # Write EQUIPMENT gains in lines
    for i in range(0, len(equipment)):

        lines.insert(gainNum + 1, 'GAIN EQUIPMENT' + '_' + equipment[
            i].Schedule_Name.replace(" ", "_").replace("-", "_").replace(".",
                                                                         "_").replace(
            "{", "").replace("}", "") + '\n')

        if equipment[i].Design_Level_Calculation_Method == "Watts":
            areaMethod = "ABSOLUTE"
            power = round(equipment[i].Design_Level, 4)
        elif equipment[i].Design_Level_Calculation_Method == "Watts/Area":
            areaMethod = "AREA_RELATED"
            power = round(equipment[i].Watts_per_Zone_Floor_Area, 4)
        else:
            areaMethod = "AREA_RELATED"
            power = 0
            log(
                "Could not find the Equipment Power Density, cause depend on the number of people (Watts/Person)",
                lg.WARNING, name="CoverterLog",
                filename="CoverterLog")

        radFract = equipment[i].Fraction_Radiant

        lines.insert(gainNum + 2, ' CONVECTIVE=' + str(
            power * (1 - radFract)) + ' : RADIATIVE=' + str(power * radFract) +
                     ' : HUMIDITY=0 : ELPOWERFRAC=1 : ' + areaMethod + ' : CATEGORY=LIGHTS\n')

    # Save file at output_folder
    if output_folder is None:
        # User did not provide an output folder path. We use the default setting
        output_folder = ar.settings.data_folder

    if not os.path.isdir(output_folder):
        os.mkdir(output_folder)

    with open(os.path.join(output_folder, "T3D_" + os.path.basename(idf)),
              "w") as converted_file:
        for line in lines:
            converted_file.write(str(line))

    log("Write data from IDF to T3D in {:,.2f} seconds".format(
        time.time() - start_time), lg.INFO, name="CoverterLog",
        filename="CoverterLog")
