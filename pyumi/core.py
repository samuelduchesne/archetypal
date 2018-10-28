import logging as lg
import time

import numpy as np
import pandas as pd

from . import settings, object_from_idf, object_from_idfs, simple_glazing
from .utils import log, label_surface, type_surface, layer_composition, schedule_composition, time2time, \
    year_composition


def convert_necb_to_umi_json(idfs, idfobjects=None):
    # if no list of idfobjects:
    if idfobjects is None:
        idfobjects = settings.useful_idf_objects

    for idf, idfobject in zip(idfs, idfobjects):
        print(object_from_idf(idf, idfobject))


def gas_type(row):
    """
    Return the UMI gas type number
    :param row: Dataframe
        row
    :return: int
        UMI gas type number
    """
    if 'air' in row['Name'].lower():
        return 0
    elif 'argon' in row['Name'].lower():
        return 1
    elif 'krypton' in row['Name'].lower():
        return 2
    elif 'xenon' in row['Name'].lower():
        return 3
    elif 'sf6' in row['Name'].lower():
        return 4


def materials_gas(idfs):
    materials_df = object_from_idfs(idfs, 'WINDOWMATERIAL:GAS')
    cols = settings.common_umi_objects['GasMaterials']

    # Add Type of gas column
    materials_df['Type'] = 'Gas'
    materials_df['GasType'] = materials_df.apply(lambda x: gas_type(x), axis=1)
    materials_df['Cost'] = 0
    materials_df['EmbodiedCarbon'] = 0
    materials_df['EmbodiedCarbonStdDev'] = 0
    materials_df['EmbodiedEnergy'] = 0
    materials_df['EmbodiedEnergyStdDev'] = 0
    materials_df['SubstitutionRatePattern'] = np.NaN  # ! Might have to change to an empty array
    materials_df['SubstitutionTimestep'] = 0
    materials_df['TransportCarbon'] = 0
    materials_df['TransportDistance'] = 0
    materials_df['TransportEnergy'] = 0
    materials_df['Life'] = 1  # TODO: What does Life mean? Always 1 in Boston Template
    materials_df['Comment'] = ''
    try:
        materials_df['DataSource'] = materials_df['Archetype']
    except Exception as e:
        log('An exception was raised while setting the DataSource of the objects', lg.WARNING)
        log('{}'.format(e), lg.ERROR)
        log('Falling back onto first IDF file containing this common object', lg.WARNING)
        materials_df['DataSource'] = 'First IDF file containing this common object'

    materials_df = materials_df.reset_index(drop=True).rename_axis('$id').reset_index()
    log('Returning {} WINDOWMATERIAL:GAS objects in a DataFrame'.format(len(materials_df)))
    return materials_df[cols].set_index('$id')  # Keep only relevant columns


def materials_glazing(idfs):
    origin_time = time.time()
    log('Initiating materials_glazing...')
    materials_df = object_from_idfs(idfs, 'WINDOWMATERIAL:GLAZING', first_occurrence_only=False)
    cols = settings.common_umi_objects['GlazingMaterials']
    cols.append('Thickness')
    column_rename = {'Optical_Data_Type': 'Optical',
                     'Window_Glass_Spectral_Data_Set_Name': 'OpticalData',
                     'Solar_Transmittance_at_Normal_Incidence': 'SolarTransmittance',
                     'Front_Side_Solar_Reflectance_at_Normal_Incidence': 'SolarReflectanceFront',
                     'Back_Side_Solar_Reflectance_at_Normal_Incidence': 'SolarReflectanceBack',
                     'Infrared_Transmittance_at_Normal_Incidence': 'IRTransmittance',
                     'Visible_Transmittance_at_Normal_Incidence': 'VisibleTransmittance',
                     'Front_Side_Visible_Reflectance_at_Normal_Incidence': 'VisibleReflectanceFront',
                     'Back_Side_Visible_Reflectance_at_Normal_Incidence': 'VisibleReflectanceBack',
                     'Front_Side_Infrared_Hemispherical_Emissivity': 'IREmissivityFront',
                     'Back_Side_Infrared_Hemispherical_Emissivity': 'IREmissivityBack',
                     'Dirt_Correction_Factor_for_Solar_and_Visible_Transmittance': 'DirtFactor'}

    # materials_df = materials_df.loc[materials_df.MaterialType == 10]
    materials_df.rename(columns=column_rename, inplace=True)
    materials_df['Comment'] = 'default'
    materials_df['Cost'] = 0
    try:
        materials_df['DataSource'] = materials_df['Archetype']
    except Exception as e:
        log('An exception was raised while setting the DataSource of the objects', lg.WARNING)
        log('{}'.format(e), lg.ERROR)
        log('Falling back onto first IDF file containing this common object', lg.WARNING)
        materials_df['DataSource'] = 'First IDF file containing this common object'

    materials_df['Density'] = 2500
    materials_df['EmbodiedCarbon'] = 0
    materials_df['EmbodiedCarbonStdDev'] = 0
    materials_df['EmbodiedEnergy'] = 0
    materials_df['EmbodiedEnergyStdDev'] = 0
    materials_df['Life'] = 1
    materials_df['SubstitutionRatePattern'] = np.NaN  # TODO: ! Might have to change to an empty array
    materials_df['SubstitutionTimestep'] = 0
    materials_df['TransportCarbon'] = 0
    materials_df['TransportDistance'] = 0
    materials_df['TransportEnergy'] = 0
    materials_df['Type'] = 'Uncoated'  # TODO Further investigation necessary

    materials_df = materials_df.reset_index(drop=True).rename_axis('$id').reset_index()

    # Now, we create glazing materials using the 'WINDOWMATERIAL:SIMPLEGLAZINGSYSTEM' objects and append them to the
    # list.
    # Try to get simple_glazing_systems
    sgs = get_simple_glazing_system(idfs)
    if not sgs.empty:
        log('Appending to WINDOWMATERIAL:GLAZING DataFrame...')
        materials_df = materials_df.set_index('$id').append(sgs, ignore_index=True, sort=True)
    materials_df = materials_df.reset_index(drop=True).rename_axis('$id').reset_index()
    # Return the Dataframe
    log('Returning {} WINDOWMATERIAL:GLAZING objects in a DataFrame'.format(len(materials_df)))
    cols.append('Archetype')
    log('Completed materials_glazing in {:,.2f} seconds\n'.format(time.time() - origin_time))
    return materials_df[cols].set_index('$id')


def materials_opaque(idfs):
    origin_time = time.time()
    log('Initiating materials_opaque...')
    mass = object_from_idfs(idfs, 'MATERIAL')
    nomass = object_from_idfs(idfs, 'MATERIAL:NOMASS')
    materials_df = pd.concat([mass, nomass], sort=True, ignore_index=True)

    cols = settings.common_umi_objects['OpaqueMaterials']
    column_rename = {'Solar_Absorptance': 'SolarAbsorptance',
                     'Specific_Heat': 'SpecificHeat',
                     'Thermal_Absorptance': 'ThermalEmittance',
                     'Thermal_Resistance': 'ThermalResistance',
                     'Visible_Absorptance': 'VisibleAbsorptance'}

    # For nomass materials, create a dummy thicness of 10cm (0.1m) and calculate 'thermal_resistance' and
    # 'conductivity' properties

    # Thermal_Resistance {m^2-K/W}
    materials_df['Thermal_Resistance'] = materials_df.apply(
        lambda x: x['Thickness'] / x['Conductivity'] if ~np.isnan(x['Conductivity']) else
        x['Thermal_Resistance'], axis=1)
    # Thickness {m}
    materials_df['Thickness'] = materials_df.apply(lambda x: 0.1 if np.isnan(x['Thickness']) else x['Thickness'],
                                                   axis=1)
    # Conductivity {W/m-K}
    materials_df['Conductivity'] = materials_df.apply(
        lambda x: x['Thickness'] / x['Thermal_Resistance'],
        axis=1)

    materials_df.rename(columns=column_rename, inplace=True)

    materials_df['Comment'] = 'default'
    materials_df['Cost'] = 0
    try:
        materials_df['DataSource'] = materials_df['Archetype']
    except Exception as e:
        log('An exception was raised while setting the DataSource of the objects', lg.WARNING)
        log('{}'.format(e), lg.ERROR)
        log('Falling back onto first IDF file containing this common object', lg.WARNING)
        materials_df['DataSource'] = 'First IDF file containing this common object'

    materials_df['EmbodiedCarbon'] = 0
    materials_df['EmbodiedCarbonStdDev'] = 0
    materials_df['EmbodiedEnergy'] = 0
    materials_df['EmbodiedEnergyStdDev'] = 0
    materials_df['Life'] = 1
    materials_df['MoistureDiffusionResistance'] = 50
    materials_df['PhaseChange'] = False
    materials_df['PhaseChangeProperties'] = ''  # TODO: Further investigation needed
    materials_df['SubstitutionRatePattern'] = np.NaN  # TODO: Might have to change to an empty array
    materials_df['SubstitutionTimestep'] = 0
    materials_df['TransportCarbon'] = 0
    materials_df['TransportDistance'] = 0
    materials_df['TransportEnergy'] = 0
    materials_df['Type'] = ''  # TODO: Further investigation necessary
    materials_df['VariableConductivity'] = False
    materials_df['VariableConductivityProperties'] = np.NaN  # TODO: Further investigation necessary

    materials_df = materials_df.reset_index(drop=True).rename_axis('$id').reset_index()
    cols.append('Thickness')
    cols.append('Archetype')
    log('Completed materials_opaque in {:,.2f} seconds\n'.format(time.time() - origin_time))
    return materials_df[cols].set_index('$id')


def constructions_opaque(idfs, opaquematerials=None):
    origin_time = time.time()
    log('Initiating constructions_opaque...')
    constructions_df = object_from_idfs(idfs, 'CONSTRUCTION', first_occurrence_only=False)
    bldg_surface_detailed = object_from_idfs(idfs, 'BUILDINGSURFACE:DETAILED', first_occurrence_only=False)

    log('Joining constructions_df on bldg_surface_detailed...')
    constructions_df = bldg_surface_detailed.join(constructions_df.set_index(['Archetype', 'Name']),
                                                  on=['Archetype', 'Construction_Name'], rsuffix='_constructions')

    constructions_df['Category'] = constructions_df.apply(lambda x: label_surface(x), axis=1)
    constructions_df['Type'] = constructions_df.apply(lambda x: type_surface(x), axis=1)

    if opaquematerials is not None:
        start_time = time.time()
        log('Initiating constructions_opaque Layer composition...')
        df = pd.DataFrame(constructions_df.set_index(['Archetype', 'Name', 'Construction_Name']).loc[:,
                          constructions_df.set_index(['Archetype', 'Name', 'Construction_Name']).columns.str.contains(
                              'Layer')].stack(), columns=['Layers']).join(
            opaquematerials.reset_index().set_index(['Archetype', 'Name']), on=['Archetype', 'Layers']).loc[:,
             ['$id', 'Thickness']].unstack(level=3).apply(lambda x: layer_composition(x), axis=1).rename('Layers')
        constructions_df = constructions_df.join(df, on=['Archetype', 'Name', 'Construction_Name'])
        log('Completed constructions_df Layer composition in {:,.2f} seconds'.format(time.time() - start_time))
    else:
        log('Could not create layer_composition because the necessary lookup DataFrame "OpaqueMaterials"  was '
            'not provided', lg.WARNING)
    cols = settings.common_umi_objects['OpaqueConstructions']

    constructions_df['AssemblyCarbon'] = 0
    constructions_df['AssemblyCost'] = 0
    constructions_df['AssemblyEnergy'] = 0
    constructions_df['Comments'] = 'default'

    try:
        constructions_df['DataSource'] = constructions_df['Archetype']
    except Exception as e:
        log('An exception was raised while setting the DataSource of the objects', lg.WARNING)
        log('{}'.format(e), lg.ERROR)
        log('Falling back onto first IDF file containing this common object', lg.WARNING)
        constructions_df['DataSource'] = 'First IDF file containing this common object'

    constructions_df['DisassemblyCarbon'] = 0
    constructions_df['DisassemblyEnergy'] = 0

    constructions_df = constructions_df.rename(columns={'Construction_Name': 'Name'})
    constructions_df = constructions_df.reset_index(drop=True).rename_axis('$id').reset_index()
    log('Completed constructions_opaque in {:,.2f} seconds\n'.format(time.time() - origin_time))
    return constructions_df[cols].set_index('$id')


def constructions_windows(idfs, material_glazing=None):
    origin_time = time.time()
    log('Initiating construction_windows...')
    constructions_df = object_from_idfs(idfs, 'CONSTRUCTION', first_occurrence_only=False)
    constructions_window_df = object_from_idfs(idfs, 'FENESTRATIONSURFACE:DETAILED', first_occurrence_only=False)
    constructions_window_df = constructions_window_df.join(constructions_df.set_index(['Archetype', 'Name']),
                                                           on=['Archetype', 'Construction_Name'],
                                                           rsuffix='_constructions')
    if material_glazing is not None:
        log('Initiating constructions_windows Layer composition...')
        start_time = time.time()
        df = pd.DataFrame(constructions_window_df.set_index(['Archetype', 'Name', 'Construction_Name']).loc[:,
                          constructions_window_df.set_index(
                              ['Archetype', 'Name', 'Construction_Name']).columns.str.contains(
                              'Layer')].stack(), columns=['Layers']).join(
            material_glazing.reset_index().set_index(['Archetype', 'Name']), on=['Archetype', 'Layers']).loc[:,
             ['$id', 'Thickness']].unstack(level=3).apply(lambda x: layer_composition(x), axis=1).rename('Layers')
        constructions_window_df = constructions_window_df.join(df, on=['Archetype', 'Name', 'Construction_Name'])
        constructions_window_df.dropna(subset=['Layers'], inplace=True)
        log('Completed constructions_window_df Layer composition in {:,.2f} seconds'.format(time.time() - start_time))
    else:
        log('Could not create layer_composition because the necessary lookup DataFrame "OpaqueMaterials"  was '
            'not provided', lg.WARNING)

    constructions_window_df.loc[:, 'AssemblyCarbon'] = 0
    constructions_window_df.loc[:, 'AssemblyCost'] = 0
    constructions_window_df.loc[:, 'AssemblyEnergy'] = 0
    constructions_window_df.loc[:, 'Category'] = 'Single'
    constructions_window_df.loc[:, 'Type'] = 2
    constructions_window_df.loc[:, 'Comments'] = 'default'

    try:
        constructions_window_df['DataSource'] = constructions_window_df['Archetype']
    except Exception as e:
        log('An exception was raised while setting the DataSource of the objects', lg.WARNING)
        log('{}'.format(e), lg.ERROR)
        log('Falling back onto first IDF file containing this common object', lg.WARNING)
        constructions_window_df['DataSource'] = 'First IDF file containing this common object'

    constructions_window_df.loc[:, 'DisassemblyCarbon'] = 0
    constructions_window_df.loc[:, 'DisassemblyEnergy'] = 0

    constructions_window_df.rename(columns={'Construction_Name': 'Name'}, inplace=True)
    constructions_window_df = constructions_window_df.reset_index(drop=True).rename_axis('$id').reset_index()

    cols = settings.common_umi_objects['WindowConstructions']
    cols.append('Archetype')
    log('Completed constructions_windows in {:,.2f} seconds\n'.format(time.time() - origin_time))
    return constructions_window_df[cols].set_index('$id')


def get_simple_glazing_system(idfs):
    try:
        materials_df = object_from_idfs(idfs, 'WINDOWMATERIAL:SIMPLEGLAZINGSYSTEM', first_occurrence_only=False)

        materials_df = materials_df.set_index(['Archetype', 'Name']).apply(
            lambda row: simple_glazing(row['Solar_Heat_Gain_Coefficient'],
                                       row['UFactor'],
                                       row['Visible_Transmittance']),
            axis=1).apply(pd.Series)
        materials_df = materials_df.reset_index()
        materials_df['Optical'] = 'SpectralAverage'
        materials_df['OpticalData'] = ''
        materials_df['DataSource'] = 'EnergyPlus Simple Glazing Calculation'
        materials_df['key'] = 'WINDOWMATERIAL:SIMPLEGLAZINGSYSTEM'
    except Exception as e:
        log('Error: {}'.format(e), lg.ERROR)
        return pd.DataFrame([])
    else:
        log('Found {} WINDOWMATERIAL:SIMPLEGLAZINGSYSTEM objects'.format(len(materials_df)))
        return materials_df


def day_schedules(idfs):
    origin_time = time.time()
    log('Initiating day_schedules...')
    schedule = object_from_idfs(idfs, 'SCHEDULE:DAY:INTERVAL', first_occurrence_only=False)
    schedule['Values'] = schedule.apply(lambda x: time2time(x), axis=1)

    cols = settings.common_umi_objects['DaySchedules']

    schedule.loc[:, 'Category'] = 'Day'
    schedule.loc[:, 'Comments'] = 'Comments'
    schedule.loc[:, 'DataSource'] = 'default'
    schedule.loc[:, 'Type'] = schedule['Schedule_Type_Limits_Name']

    schedule = schedule.reset_index(drop=True).rename_axis('$id').reset_index()
    cols.append('Archetype')
    log('Completed day_schedules in {:,.2f} seconds\n'.format(time.time() - origin_time))
    return schedule[cols].set_index('$id')


def week_schedules(idfs, dayschedules=None):
    origin_time = time.time()
    log('Initiating week_schedules...')
    schedule = object_from_idfs(idfs, 'SCHEDULE:WEEK:DAILY', first_occurrence_only=False)
    cols = settings.common_umi_objects['WeekSchedules']

    if dayschedules is not None:
        start_time = time.time()
        df = pd.DataFrame(schedule.set_index(['Archetype', 'Name']).loc[:,
                          schedule.set_index(['Archetype', 'Name']).columns.str.contains('Schedule')].stack(),
                          columns=['Schedule']).join(dayschedules.reset_index().set_index(['Archetype', 'Name']),
                                                     on=['Archetype', 'Schedule']).loc[:, ['$id', 'Values']].unstack(
            level=2).apply(lambda x: schedule_composition(x), axis=1).rename('Days')
        schedule = schedule.join(df, on=['Archetype', 'Name'])
        log('Completed week_schedules schedule composition in {:,.2f} seconds'.format(time.time() - start_time))
    else:
        log('Could not create layer_composition because the necessary lookup DataFrame "DaySchedules"  was '
            'not provided', lg.WARNING)

    schedule.loc[:, 'Category'] = 'Week'
    schedule.loc[:, 'Comments'] = 'default'
    schedule.loc[:, 'DataSource'] = schedule['Archetype']

    # Copy the Schedule Type Over
    schedule = schedule.join(dayschedules.set_index(['Archetype', 'Name']).loc[:, ['Type']],
                             on=['Archetype', 'Monday_ScheduleDay_Name'])

    schedule = schedule.reset_index(drop=True).rename_axis('$id').reset_index()
    cols.append('Archetype')
    log('Completed day_schedules in {:,.2f} seconds\n'.format(time.time() - origin_time))
    return schedule[cols].set_index('$id')


def year_schedules(idfs, weekschedule=None):
    origin_time = time.time()
    log('Initiating week_schedules...')
    schedule = object_from_idfs(idfs, 'SCHEDULE:YEAR', first_occurrence_only=False)
    cols = settings.common_umi_objects['YearSchedules']

    if weekschedule is not None:
        start_time = time.time()
        df = pd.DataFrame(schedule.set_index(['Archetype', 'Name']).drop(['index', 'key', 'Schedule_Type_Limits_Name'],
                                                                         axis=1).stack(),
                          columns=['Schedules']).reset_index().join(
            weekschedule.reset_index().set_index(['Archetype', 'Name']), on=['Archetype', 'Schedules']).set_index(
            ['Archetype', 'Name','level_2']).drop(['Category', 'Comments', 'DataSource', 'Days', 'Type'],
                                                   axis=1).unstack().apply(lambda x: year_composition(x),
                                                                           axis=1).rename('Parts')
        schedule = schedule.join(df, on=['Archetype', 'Name'])
        log('Completed week_schedules schedule composition in {:,.2f} seconds'.format(time.time() - start_time))
    else:
        log('Could not create layer_composition because the necessary lookup DataFrame "WeekSchedule"  was '
            'not provided', lg.WARNING)

    schedule['Category'] = 'Year'
    schedule['Comments'] = 'default'
    schedule['DataSource'] = schedule['Archetype']

    schedule = schedule.join(weekschedule.set_index(['Archetype', 'Name']).loc[:, ['Type']],
                             on=['Archetype', 'ScheduleWeek_Name_1'])

    schedule = schedule.reset_index(drop=True).rename_axis('$id').reset_index()
    cols.append('Archetype')
    log('Completed day_schedules in {:,.2f} seconds\n'.format(time.time() - origin_time))
    return schedule[cols].set_index('$id')