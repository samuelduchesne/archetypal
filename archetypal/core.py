import logging as lg
import time

import numpy as np
import pandas as pd

from . import settings, object_from_idf, object_from_idfs, simple_glazing, iscore, weighted_mean, top, run_eplus, \
    load_idf
from .utils import log, label_surface, type_surface, layer_composition, schedule_composition, time2time, \
    year_composition


class Template:
    """

    """
    materials_opaque = ...  # type: pd.DataFrame
    materials_glazing = ...  # type: pd.DataFrame
    materials_gas = ...  # type: pd.DataFrame

    def __init__(self, idf_files, weather, load=False, **kwargs):
        """Initializes a Template class

        Args:
            idf_files:
            weather (str):
            load:
            **kwargs:
        """
        self.idf_files = idf_files
        self.idfs = load_idf(self.idf_files, **kwargs)
        self.weather = weather

        # Umi stuff
        self.materials_gas = None
        self.materials_glazing = None
        self.materials_opaque = None
        self.constructions_opaque = None
        self.constructions_windows = None
        self.day_schedules = None
        self.week_schedules = None
        self.year_schedules = None

        if load:
            self.read()

        self.sql = None

    def read(self):
        # Umi stuff
        self.materials_gas = materials_gas(self.idfs)
        self.materials_glazing = materials_glazing(self.idfs)
        self.materials_opaque = materials_opaque(self.idfs)
        self.constructions_opaque = constructions_opaque(self.idfs, self.materials_opaque)
        self.constructions_windows = constructions_windows(self.idfs, self.materials_glazing)
        self.day_schedules = day_schedules(self.idfs)
        self.week_schedules = week_schedules(self.idfs, self.day_schedules)
        self.year_schedules = year_schedules(self.idfs, self.week_schedules)

    def run_eplus(self, silent=True, **kwargs):
        """

        """
        self.sql = run_eplus(self.idf_files, self.weather, output_report='sql', **kwargs)
        if not silent:
            return self.sql


def convert_necb_to_umi_json(idfs, idfobjects=None):
    # if no list of idfobjects:
    if idfobjects is None:
        idfobjects = settings.useful_idf_objects

    for idf, idfobject in zip(idfs, idfobjects):
        print(object_from_idf(idf, idfobject))


def gas_type(row):
    """Return the UMI gas type number

    Args:
        row (pandas.DataFrame):

    Returns:
        int: UMI gas type number

        The return number is specific the umi api.

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
    """Gas group

    Args:
        idfs: parsed IDF files

    Returns:
        padnas.DataFrame: Returns a DataFrame with the all necessary Umi columns
    """
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
    """Material Glazing group

    Args:
        idfs (list or dict): parsed IDF files

    Returns:
        padnas.DataFrame: Returns a DataFrame with the all necessary Umi columns
    """
    origin_time = time.time()
    log('Initiating materials_glazing...')
    materials_df = object_from_idfs(idfs, 'WINDOWMATERIAL:GLAZING', first_occurrence_only=False)
    cols = settings.common_umi_objects['GlazingMaterials'].copy()
    cols.pop(0)  # remove $id
    cols.append('Thickness')
    cols.append('Archetype')
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
    materials_df = materials_df.rename(columns=column_rename)
    materials_df = materials_df.reindex(columns=cols)
    materials_df = materials_df.fillna({'DirtFactor': 1.0})
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

    materials_df = materials_df.reset_index(drop=True).rename_axis('$id')

    # Now, we create glazing materials using the 'WINDOWMATERIAL:SIMPLEGLAZINGSYSTEM' objects and append them to the
    # list.
    # Try to get simple_glazing_systems
    sgs = get_simple_glazing_system(idfs)
    if not sgs.empty:
        log('Appending to WINDOWMATERIAL:GLAZING DataFrame...')
        materials_df = materials_df.append(sgs, ignore_index=True, sort=True).reset_index(
            drop=True).rename_axis('$id')
    # Return the Dataframe
    log('Returning {} WINDOWMATERIAL:GLAZING objects in a DataFrame'.format(len(materials_df)))
    log('Completed materials_glazing in {:,.2f} seconds\n'.format(time.time() - origin_time))
    return materials_df[cols]


def materials_opaque(idfs):
    """Opaque Material group

    Args:
        idfs (list or dict): parsed IDF files

    Returns:
        padnas.DataFrame: Returns a DataFrame with the all necessary Umi columns
    """
    origin_time = time.time()
    log('Initiating materials_opaque...')
    mass = object_from_idfs(idfs, 'MATERIAL')
    nomass = object_from_idfs(idfs, 'MATERIAL:NOMASS')
    materials_df = pd.concat([mass, nomass], sort=True, ignore_index=True)

    cols = settings.common_umi_objects['OpaqueMaterials'].copy()
    cols.pop(0)  # Pop $id
    cols.append('Thickness')
    cols.append('Archetype')
    cols.append('ThermalResistance')
    column_rename = {'Solar_Absorptance': 'SolarAbsorptance',
                     'Specific_Heat': 'SpecificHeat',
                     'Thermal_Absorptance': 'ThermalEmittance',
                     'Thermal_Resistance': 'ThermalResistance',
                     'Visible_Absorptance': 'VisibleAbsorptance'}
    # Rename columns
    materials_df = materials_df.rename(columns=column_rename)
    materials_df = materials_df.reindex(columns=cols)
    # Thermal_Resistance {m^2-K/W}
    materials_df['ThermalResistance'] = materials_df.apply(
        lambda x: x['Thickness'] / x['Conductivity'] if ~np.isnan(x['Conductivity']) else
        x['ThermalResistance'], axis=1)

    # Fill nan values (nomass materials) with defaults
    materials_df = materials_df.fillna({'Thickness': 0.0127,  # half inch tichness
                                        'Density': 1,  # 1 kg/m3, smallest value umi allows
                                        'SpecificHeat': 100,  # 100 J/kg-K, smallest value umi allows
                                        'SolarAbsorptance': 0.7,  # default value
                                        'SubstitutionTimestep': 0,  # default value
                                        'ThermalEmittance': 0.9,  # default value
                                        'VariableConductivityProperties': 0,  # default value
                                        'VisibleAbsorptance': 0.8,  # default value
                                        })
    # Calculate Conductivity {W/m-K}
    materials_df['Conductivity'] = materials_df.apply(
        lambda x: x['Thickness'] / x['ThermalResistance'],
        axis=1)

    # Fill other necessary columns
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

    materials_df = materials_df.reset_index(drop=True).rename_axis('$id')
    log('Completed materials_opaque in {:,.2f} seconds\n'.format(time.time() - origin_time))
    return materials_df[cols]


def constructions_opaque(idfs, opaquematerials=None):
    """Opaque Construction group

    Args:
        idfs (list or dict): parsed IDF files
        opaquematerials (pandas.DataFrame): DataFrame generated by `materials_opaque()`

    Returns:
        padnas.DataFrame: Returns a DataFrame with the all necessary Umi columns

    """
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
    """Window Construction group

    Args:
        idfs (list or dict): parsed IDF files
        material_glazing (pandas.DataFrame): DataFrame generated by :func:`materials_glazing`

    Returns:
        padnas.DataFrame: Returns a DataFrame with the all necessary Umi columns

    """
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
    """Retreives all simple glazing objects from a list of IDF files. Calls :func:`simple_glazing` in order to calculate a
    new glazing system that has the same properties.

    Args:
        idfs (list or dict): parsed IDF files

    Returns:
        pandas.DataFrame : A DataFrame

    """
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
        materials_df['DataSource'] = materials_df.apply(lambda row: 'EnergyPlus Simple Glazing Calculation {' \
                                                                    'shgc:{:.2f}, u-value:{:.2f}, ' \
                                                                    't_vis:{:.2f}}'.format(
            row['Solar_Heat_Gain_Coefficient'],
            row['UFactor'],
            row['Visible_Transmittance']))
        materials_df['key'] = 'WINDOWMATERIAL:SIMPLEGLAZINGSYSTEM'
    except Exception as e:
        log('Error: {}'.format(e), lg.ERROR)
        return pd.DataFrame([])
    else:
        log('Found {} WINDOWMATERIAL:SIMPLEGLAZINGSYSTEM objects'.format(len(materials_df)))
        return materials_df


def day_schedules(idfs):
    """Parses daily schedules of type 'SCHEDULE:DAY:INTERVAL'

    Args:
        idfs (list of dict): parsed IDF files

    Returns:

    """
    origin_time = time.time()
    log('Initiating day_schedules...')
    schedule = object_from_idfs(idfs, 'SCHEDULE:DAY:INTERVAL', first_occurrence_only=False)
    if not schedule.empty:
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
    else:
        log('Returning Empty DataFrame', lg.WARNING)
        return pd.DataFrame({'Day Schedules': []})


def week_schedules(idfs, dayschedules=None):
    """Parses daily schedules of type 'SCHEDULE:WEEK:DAILY'

    Args:
        idfs (list or dict): parsed IDF files
        dayschedules (pandas.DataFrame): DataFrame generated by :func:`day_schedules`

    Returns:

    """
    origin_time = time.time()
    log('Initiating week_schedules...')
    schedule = object_from_idfs(idfs, 'SCHEDULE:WEEK:DAILY', first_occurrence_only=False)
    if not schedule.empty:
        cols = settings.common_umi_objects['WeekSchedules']

        if dayschedules is not None:
            start_time = time.time()
            df = pd.DataFrame(schedule.set_index(['Archetype', 'Name']).loc[:,
                              schedule.set_index(['Archetype', 'Name']).columns.str.contains('Schedule')].stack(),
                              columns=['Schedule']).join(dayschedules.reset_index().set_index(['Archetype', 'Name']),
                                                         on=['Archetype', 'Schedule']).loc[:,
                 ['$id', 'Values']].unstack(
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
    else:
        log('Returning Empty DataFrame', lg.WARNING)
        return pd.DataFrame({'Week Schedules': []})


def year_schedules(idfs, weekschedule=None):
    """Parses daily schedules of type 'SCHEDULE:YEAR'

    Args:
        idfs (list or dict): parsed IDF files
        weekschedule (pandas.DataFrame): DataFrame generated by :func:`week_schedules`

    Returns:

    """
    origin_time = time.time()
    log('Initiating week_schedules...')
    schedule = object_from_idfs(idfs, 'SCHEDULE:YEAR', first_occurrence_only=False)
    if not schedule.empty:
        cols = settings.common_umi_objects['YearSchedules']

        if weekschedule is not None:
            start_time = time.time()
            df = pd.DataFrame(
                schedule.set_index(['Archetype', 'Name']).drop(['index', 'key', 'Schedule_Type_Limits_Name'],
                                                               axis=1).stack(),
                columns=['Schedules']).reset_index().join(
                weekschedule.reset_index().set_index(['Archetype', 'Name']), on=['Archetype', 'Schedules']).set_index(
                ['Archetype', 'Name', 'level_2']).drop(['Category', 'Comments', 'DataSource', 'Days', 'Type'],
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
    else:
        log('Returning Empty DataFrame', lg.WARNING)
        return pd.DataFrame({'Year Schedules': []})


def zone_loads(df):
    """Takes the sql reports (as a dict of DataFrames), concatenates all relevant 'Initialization Summary' tables and
    applies a series of aggragation functions (weighted means and "top").

    Args:
        df (dict): A dict of pandas.DataFrames

    Returns:
        pandas.DataFrame : A new DataFrame with aggragated values

    """

    # Loading each section in a dictionnary. Used to create a new DF using pd.concat()
    d = {'Zones': zone_information(df).reset_index().set_index(['Archetype', 'Zone Name']),
         'NominalLighting': nominal_lighting(df).reset_index().set_index(['Archetype', 'Zone Name']),
         'NominalPeople': nominal_people(df).reset_index().set_index(['Archetype', 'Zone Name']),
         'NominalInfiltration': nominal_infiltration(df).reset_index().set_index(['Archetype', 'Zone Name']),
         'NominalEquipment': nominal_equipment(df).reset_index().set_index(['Archetype', 'Zone Name'])}

    df = (pd.concat(d, axis=1, keys=d.keys())
          .dropna(axis=0, how='all', subset=[('Zones', 'Type')])  # Drop rows that are all nans
          .reset_index(level=1, col_level=1, col_fill='Zones')  # Reset Index level to get Zone Name
          .reset_index().set_index(['Archetype', ('Zones', 'RowName')])
          .rename_axis(['Archetype', 'RowName']))

    df[('Zones', 'Zone Type')] = df.apply(lambda x: iscore(x), axis=1)

    df = df.reset_index().groupby(['Archetype', ('Zones', 'Zone Type')]).apply(
        lambda x: zoneloads_aggregation(x.set_index(['Archetype', 'RowName'])))
    return df


def zone_ventilation(df):
    """Takes the sql reports (as a dict of DataFrames), concatenates all relevant 'Initialization Summary' tables and
    applies a series of aggragation functions (weighted means and "top").

    Args:
        df (dict): A dict of pandas.DataFrames

    Returns:
        pandas.DataFrame:

    """
    nominal_infiltration(df).reset_index().set_index(['Archetype', 'Zone Name'])

    # Loading each section in a dictionnary. Used to create a new DF using pd.concat()
    d = {'Zones': zone_information(df).reset_index().set_index(['Archetype', 'Zone Name']),
         'NominalInfiltration': nominal_infiltration(df).reset_index().set_index(['Archetype', 'Zone Name']),
         'NominalScheduledVentilation':
             nominal_ventilation(df).reset_index().set_index(['Archetype',
                                                              'Zone Name']).loc[
             lambda e: e['Fan Type {Exhaust;Intake;Natural}'].str.contains('Natural'), :],
         'NominalNaturalVentilation':
             nominal_ventilation(df).reset_index().set_index(['Archetype',
                                                              'Zone Name']).loc[
             lambda e: ~e['Fan Type {Exhaust;Intake;Natural}'].str.contains('Natural'), :]}

    df = (pd.concat(d, axis=1, keys=d.keys())
          .dropna(axis=0, how='all', subset=[('Zones', 'Type')])  # Drop rows that are all nans
          .reset_index(level=1, col_level=1, col_fill='Zones')  # Reset Index level to get Zone Name
          .reset_index().set_index(['Archetype', ('Zones', 'RowName')])
          .rename_axis(['Archetype', 'RowName']))

    df[('Zones', 'Zone Type')] = df.apply(lambda x: iscore(x), axis=1)

    df = df.reset_index().groupby(
        ['Archetype', ('Zones', 'Zone Type')]).apply(
        lambda x: zoneventilation_aggregation(x.set_index(['Archetype', 'RowName'])))

    return df


def zoneloads_aggregation(x):
    """Set of different zoneloads_aggregation (weighted mean and "top") on multiple objects, eg. ('NominalLighting',
    'Lights/Floor Area {W/m2}').

    All the DataFrame is passed to each function.

    Returns a Series with a MultiIndex

    Args:
        x (pandas.DataFrame):

    Returns:
        pandas.Series: Series with a MultiIndex

    """
    area_m_ = [('Zones', 'Floor Area {m2}'), ('Zones', 'Zone Multiplier')]  # Floor area and zone multiplier
    d = {('NominalLighting', 'weighted mean'):
             weighted_mean(x[('NominalLighting', 'Lights/Floor Area {W/m2}')], x, area_m_),
         ('NominalLighting', 'top'):
             top(x[('NominalLighting', 'Schedule Name')], x, area_m_),
         ('NominalPeople', 'weighted mean'):
             weighted_mean(x[('NominalPeople', 'People/Floor Area {person/m2}')], x, area_m_),
         ('NominalPeople', 'top'):
             top(x[('NominalPeople', 'Schedule Name')], x, area_m_),
         ('NominalEquipment', 'weighted mean'):
             weighted_mean(x[('NominalEquipment', 'Equipment/Floor Area {W/m2}')], x, area_m_),
         ('NominalEquipment', 'top'):
             top(x[('NominalEquipment', 'Schedule Name')], x, area_m_)
         }

    return pd.Series(d)


def zoneventilation_aggregation(x):
    """Set of different zoneventilation_aggregation (weighted mean and "top") on multiple objects,
    eg. ('NominalVentilation', 'ACH - Air Changes per Hour').

    All the DataFrame is passed to each function.

    Returns a Series with a MultiIndex

    Args:
        x (pandas.DataFrame):

    Returns:
        pandas.Series: Series with a MultiIndex

    Todo: infiltration for plenums should not be taken into account

    """
    area_m_ = [('Zones', 'Floor Area {m2}'), ('Zones', 'Zone Multiplier')]  # Floor area and zone multiplier

    d = {('Infiltration', 'weighted mean {ACH}'): (
        weighted_mean(x[('NominalInfiltration', 'ACH - Air Changes per Hour')], x, area_m_)),
        ('Infiltration', 'Top Schedule Name'): (
            top(x[('NominalInfiltration', 'Schedule Name')], x, area_m_)),
        ('ScheduledVentilation', 'weighted mean {ACH}'): (
            weighted_mean(x[('NominalScheduledVentilation', 'ACH - Air Changes per Hour')], x,
                          area_m_)),
        ('ScheduledVentilation', 'Top Schedule Name'): (
            top(x[('NominalScheduledVentilation', 'Schedule Name')], x, area_m_)),
        ('ScheduledVentilation', 'Setpoint'): (
            top(x[('NominalScheduledVentilation', 'Minimum Indoor Temperature{C}/Schedule')], x,
                area_m_)),
        ('NatVent', 'weighted mean {ACH}'): (
            weighted_mean(x[('NominalNaturalVentilation', 'ACH - Air Changes per Hour')], x,
                          area_m_)),
        ('NatVent', 'Top Schedule Name'): (
            top(x[('NominalNaturalVentilation', 'Schedule Name')], x, area_m_)),
        ('NatVent', 'MaxOutdoorAirTemp'): (
            top(x[('NominalNaturalVentilation', 'Maximum Outdoor Temperature{C}/Schedule')], x,
                area_m_)),
        ('NatVent', 'MinOutdoorAirTemp'): (
            top(x[('NominalNaturalVentilation', 'Minimum Outdoor Temperature{C}/Schedule')], x,
                area_m_)),
        ('NatVent', 'ZoneTempSetpoint'): (
            top(x[('NominalNaturalVentilation', 'Minimum Indoor Temperature{C}/Schedule')], x,
                area_m_))}

    return pd.Series(d)


def nominal_lighting(df):
    """Nominal lighting

    Args:
        df:

    Returns:

    """
    df = get_from_tabulardata(df)
    tbstr = df[(df.ReportName == 'Initialization Summary') &
               (df.TableName == 'Lights Internal Gains Nominal')].reset_index()

    tbpiv = tbstr.pivot_table(index=['Archetype', 'RowName'],
                              columns='ColumnName',
                              values='Value',
                              aggfunc=lambda x: ' '.join(x))
    tbpiv = tbpiv.replace({'N/A': np.nan}).apply(lambda x: pd.to_numeric(x, errors='ignore'))
    tbpiv = tbpiv.reset_index().groupby(['Archetype', 'Zone Name']).apply(nominal_lighting_aggregation)
    return tbpiv.reset_index().groupby(['Archetype', 'Zone Name']).agg(
        lambda x: pd.to_numeric(x, errors='ignore').sum())


def nominal_people(df):
    """Nominal People

    References:
        * `NominalPeople Table <https://bigladdersoftware.com/epx/docs/8-9/output-details-and-examples/eplusout-sql.html
          #nominalpeople-table>`_

    Args:
        df:

    Returns:

    """
    df = get_from_tabulardata(df)
    tbstr = df[(df.ReportName == 'Initialization Summary') &
               (df.TableName == 'People Internal Gains Nominal')].reset_index()

    tbpiv = tbstr.pivot_table(index=['Archetype', 'RowName'],
                              columns='ColumnName',
                              values='Value',
                              aggfunc=lambda x: ' '.join(x))
    tbpiv.replace({'N/A': np.nan}, inplace=True)
    return tbpiv.reset_index().groupby(['Archetype', 'Zone Name']).agg(
        lambda x: pd.to_numeric(x, errors='ignore').sum())


def nominal_equipment(df):
    """Nominal Electric Equipment

    References:
        * `NominalElectricEquipment Table <https://bigladdersoftware.com/epx/docs/8-9/output-details-and-examples
          /eplusout-sql.html#nominalelectricequipment-table>`_


    Args:
        df:

    Returns:

    """
    df = get_from_tabulardata(df)
    tbstr = df[(df.ReportName == 'Initialization Summary') &
               (df.TableName == 'ElectricEquipment Internal Gains Nominal')].reset_index()

    tbpiv = tbstr.pivot_table(index=['Archetype', 'RowName'],
                              columns='ColumnName',
                              values='Value',
                              aggfunc=lambda x: ' '.join(x))
    tbpiv = tbpiv.replace({'N/A': np.nan}).apply(lambda x: pd.to_numeric(x, errors='ignore'))
    tbpiv = tbpiv.reset_index().groupby(['Archetype', 'Zone Name']).apply(nominal_equipment_aggregation)
    return tbpiv


def nominal_infiltration(df):
    """

    Args:
        df:

    Returns:

    """
    df = get_from_tabulardata(df)
    tbstr = df[(df.ReportName == 'Initialization Summary') &
               (df.TableName == 'ZoneInfiltration Airflow Stats Nominal')].reset_index()

    tbpiv = tbstr.pivot_table(index=['Archetype', 'RowName'],
                              columns='ColumnName',
                              values='Value',
                              aggfunc=lambda x: ' '.join(x))
    tbpiv.replace({'N/A': np.nan}, inplace=True)
    return tbpiv.reset_index().groupby(['Archetype', 'Zone Name']).agg(
        lambda x: pd.to_numeric(x, errors='ignore').sum())


def nominal_ventilation(df):
    """

    Args:
        df:

    Returns:

    """
    df = get_from_tabulardata(df)
    tbstr = df[(df.ReportName == 'Initialization Summary') &
               (df.TableName == 'ZoneVentilation Airflow Stats Nominal')].reset_index()

    tbpiv = tbstr.pivot_table(index=['Archetype', 'RowName'],
                              columns='ColumnName',
                              values='Value',
                              aggfunc=lambda x: ' '.join(x))

    tbpiv = tbpiv.replace({'N/A': np.nan}).apply(lambda x: pd.to_numeric(x, errors='ignore'))
    tbpiv = tbpiv.reset_index().groupby(['Archetype',
                                         'Zone Name',
                                         'Fan Type {Exhaust;Intake;Natural}']).apply(nominal_ventilation_aggregation)
    return tbpiv
    # .reset_index().groupby(['Archetype', 'Zone Name']).agg(
    # lambda x: pd.to_numeric(x, errors='ignore').sum())


def nominal_lighting_aggregation(x):
    """
    Aggregates the lighting equipments whithin a single zone name (implies that .groupby(['Archetype',
    'Zone Name']) is performed before calling this function).

    Args:
        x (pandas.DataFrame): x

    Returns:
        pandas.DataFrame: A DataFrame with at least one entry per ('Archetype', 'Zone Name'), aggregated accordingly.

    """
    how_dict = {'# Zone Occupants': x['# Zone Occupants'].sum(),
                'End-Use Category': top(x['End-Use Category'], x, 'Zone Floor Area {m2}'),
                'Fraction Convected': weighted_mean(x['Fraction Convected'], x, 'Lighting Level {W}'),
                'Fraction Radiant': weighted_mean(x['Fraction Radiant'], x, 'Lighting Level {W}'),
                'Fraction Replaceable': weighted_mean(x['Fraction Replaceable'], x, 'Lighting Level {W}'),
                'Fraction Return Air': weighted_mean(x['Fraction Return Air'], x, 'Lighting Level {W}'),
                'Fraction Short Wave': weighted_mean(x['Fraction Short Wave'], x, 'Lighting Level {W}'),
                'Lighting Level {W}': x['Lighting Level {W}'].sum(),
                'Lights per person {W/person}': x['Lights per person {W/person}'].sum(),
                'Lights/Floor Area {W/m2}': x['Lights/Floor Area {W/m2}'].sum(),
                'Name': '+'.join(x['Name']),
                'Nominal Maximum Lighting Level {W}': x['Nominal Maximum Lighting Level {W}'].sum(),
                'Nominal Minimum Lighting Level {W}': x['Nominal Minimum Lighting Level {W}'].sum(),
                'Schedule Name': top(x['Schedule Name'], x, 'Lighting Level {W}'),
                # todo: The schedule could be an aggregation by itself
                'Zone Floor Area {m2}': x['Zone Floor Area {m2}'].sum()}

    try:
        df = pd.DataFrame(how_dict, index=range(0, 1))  # range should always be one since we are trying to merge zones
    except Exception as e:
        print('{}'.format(e))
    return df


def nominal_equipment_aggregation(x):
    """
    Aggregates the equipments whithin a single zone name (implies that .groupby(['Archetype',
    'Zone Name']) is performed before calling this function).

    Args:
        x (pandas.DataFrame): x

    Returns:
        pandas.DataFrame: A DataFrame with at least one entry per ('Archetype', 'Zone Name'), aggregated accordingly.

    """
    how_dict = {'# Zone Occupants': x['# Zone Occupants'].sum(),
                'End-Use SubCategory': top(x['End-Use SubCategory'], x, 'Zone Floor Area {m2}'),
                'Equipment Level {W}': x['Equipment Level {W}'].sum(),
                'Equipment per person {W/person}': x['Equipment per person {W/person}'].sum(),
                'Equipment/Floor Area {W/m2}': x['Equipment/Floor Area {W/m2}'].sum(),
                'Fraction Convected': weighted_mean(x['Fraction Convected'], x, 'Equipment Level {W}'),
                'Fraction Latent': weighted_mean(x['Fraction Latent'], x, 'Equipment Level {W}'),
                'Fraction Lost': weighted_mean(x['Fraction Lost'], x, 'Equipment Level {W}'),
                'Fraction Radiant': weighted_mean(x['Fraction Radiant'], x, 'Equipment Level {W}'),
                'Name': '+'.join(x['Name']),
                'Nominal Maximum Equipment Level {W}': x['Nominal Maximum Equipment Level {W}'].sum(),
                'Nominal Minimum Equipment Level {W}': x['Nominal Minimum Equipment Level {W}'].sum(),
                'Schedule Name': top(x['Schedule Name'], x, 'Equipment Level {W}'),
                # todo: The schedule could be an aggregation by itself
                'Zone Floor Area {m2}': x['Zone Floor Area {m2}'].sum()}

    try:
        df = pd.DataFrame(how_dict, index=range(0, 1))  # range should always be one since we are trying to merge zones
    except Exception as e:
        print('{}'.format(e))
    return df


def nominal_ventilation_aggregation(x):
    """
    Aggregates the ventilations whithin a single zone name (implies that .groupby(['Archetype',
    'Zone Name']) is performed before calling this function).

    Args:
        x:

    Returns:
        A DataFrame with at least one entry per ('Archetype', 'Zone Name'), aggregated accordingly.
    """
    how_dict = {'Name': top(x['Name'], x, 'Zone Floor Area {m2}'),
                'Schedule Name': top(x['Schedule Name'], x, 'Zone Floor Area {m2}'),
                'Zone Floor Area {m2}': top(x['Zone Floor Area {m2}'], x, 'Zone Floor Area {m2}'),
                '# Zone Occupants': top(x['# Zone Occupants'], x, 'Zone Floor Area {m2}'),
                'Design Volume Flow Rate {m3/s}': weighted_mean(x['Design Volume Flow Rate {m3/s}'], x,
                                                                'Zone Floor Area {m2}'),
                'Volume Flow Rate/Floor Area {m3/s/m2}': weighted_mean(x['Volume Flow Rate/Floor Area {m3/s/m2}'],
                                                                       x, 'Zone Floor Area {m2}'),
                'Volume Flow Rate/person Area {m3/s/person}': weighted_mean(
                    x['Volume Flow Rate/person Area {m3/s/person}'], x, 'Zone Floor Area {m2}'),
                'ACH - Air Changes per Hour': weighted_mean(x['ACH - Air Changes per Hour'], x,
                                                            'Zone Floor Area {m2}'),
                'Fan Pressure Rise {Pa}': weighted_mean(x['Fan Pressure Rise {Pa}'], x,
                                                        'Zone Floor Area {m2}'),
                'Fan Efficiency {}': weighted_mean(x['Fan Efficiency {}'], x,
                                                   'Zone Floor Area {m2}'),
                'Equation A - Constant Term Coefficient {}': top(x['Equation A - Constant Term Coefficient {}'], x,
                                                                 'Zone Floor Area {m2}'),
                'Equation B - Temperature Term Coefficient {1/C}': top(x['Equation B - Temperature Term Coefficient {'
                                                                         '1/C}'], x, 'Zone Floor Area {m2}'),
                'Equation C - Velocity Term Coefficient {s/m}': top(x['Equation C - Velocity Term Coefficient {s/m}'],
                                                                    x,
                                                                    'Zone Floor Area {m2}'),
                'Equation D - Velocity Squared Term Coefficient {s2/m2}': top(
                    x['Equation D - Velocity Squared Term Coefficient {s2/m2}'], x, 'Zone Floor Area {m2}'),
                'Minimum Indoor Temperature{C}/Schedule': top(x['Minimum Indoor Temperature{C}/Schedule'], x,
                                                              'Zone Floor Area {m2}'),
                'Maximum Indoor Temperature{C}/Schedule': top(x['Maximum Indoor Temperature{C}/Schedule'], x,
                                                              'Zone Floor Area {m2}'),
                'Delta Temperature{C}/Schedule': top(x['Delta Temperature{C}/Schedule'], x, 'Zone Floor Area {m2}'),
                'Minimum Outdoor Temperature{C}/Schedule': top(x['Minimum Outdoor Temperature{C}/Schedule'], x,
                                                               'Zone Floor Area {m2}'),
                'Maximum Outdoor Temperature{C}/Schedule': top(x['Maximum Outdoor Temperature{C}/Schedule'], x,
                                                               'Zone Floor Area {m2}'),
                'Maximum WindSpeed{m/s}': top(x['Maximum WindSpeed{m/s}'], x, 'Zone Floor Area {m2}')}
    try:
        df = pd.DataFrame(how_dict, index=range(0, 1))  # range should always be one since we are trying to merge zones
    except Exception as e:
        print('{}'.format(e))
    return df


def get_from_tabulardata(results):
    """
    Returns a DataFrame from the 'TabularDataWithStrings' table. A multiindex is returned with names [
    'Archetype', 'Index']

    Args:
        results:

    Returns:

    """
    tab_data_wstring = pd.concat([value['TabularDataWithStrings'] for value in results.values()],
                                 keys=results.keys(), names=['Archetype'])
    tab_data_wstring.index.names = ['Archetype', 'Index']  #
    return tab_data_wstring


def get_from_reportdata(results):
    """
    Returns a DataFrame from the 'ReportData' table. A multiindex is returned with names [
    'Archetype', 'Index']

    Args:
        results:

    Returns:

    """
    report_data = pd.concat([value['ReportData'] for value in results.values()],
                            keys=results.keys(), names=['Archetype'])
    report_data['ReportDataDictionaryIndex'] = pd.to_numeric(report_data['ReportDataDictionaryIndex'])

    report_data_dict = pd.concat([value['ReportDataDictionary'] for value in results.values()],
                                 keys=results.keys(), names=['Archetype'])

    return report_data.reset_index().join(report_data_dict, on=['Archetype', 'ReportDataDictionaryIndex'])


def zone_information(df):
    """

    Args:
        df:

    Returns:

    """
    df = get_from_tabulardata(df)
    tbstr = df[(df.ReportName == 'Initialization Summary') &
               (df.TableName == 'Zone Information')].reset_index()
    # Ignore Zones that are not part of building area
    pivoted = tbstr.pivot_table(index=['Archetype', 'RowName'],
                                columns='ColumnName',
                                values='Value',
                                aggfunc=lambda x: ' '.join(x))

    return pivoted.loc[pivoted['Part of Total Building Area'] == 'Yes', :]


def zoneconditioning_aggregation(x):
    d = {}
    area_m_ = [('Zones', 'Zone Multiplier'), ('Zones', 'Floor Area {m2}')]

    d[('COP Heating', 'weighted mean {}')] = (
        weighted_mean(x[('COP', 'COP Heating')], x, area_m_))

    d[('COP Cooling', 'weighted mean {}')] = (
        weighted_mean(x[('COP', 'COP Cooling')], x, area_m_))

    d[('ZoneCooling', 'designday')] = \
        np.nanmean(x.loc[x[('ZoneCooling', 'Thermostat Setpoint Temperature at Peak Load')] > 0,
                         ('ZoneCooling', 'Thermostat Setpoint Temperature at Peak Load')])

    d[('ZoneHeating', 'designday')] = \
        np.nanmean(x.loc[x[('ZoneHeating', 'Thermostat Setpoint Temperature at Peak Load')] > 0,
                         ('ZoneHeating', 'Thermostat Setpoint Temperature at Peak Load')])

    d[('MinFreshAirPerArea', 'weighted average {m3/s-m2}')] = \
        max(weighted_mean(x[('ZoneCooling', 'Minimum Outdoor Air Flow Rate')].astype(float)
                          / x.loc[:, ('Zones', 'Floor Area {m2}')].astype(float),
                          x,
                          area_m_),
            weighted_mean(x[('ZoneHeating', 'Minimum Outdoor Air Flow Rate')].astype(float)
                          / x[('Zones', 'Floor Area {m2}')].astype(float),
                          x,
                          area_m_))

    d[('MinFreshAirPerPerson', 'weighted average {m3/s-person}')] = \
        max(weighted_mean(x[('ZoneCooling', 'Minimum Outdoor Air Flow Rate')].astype(float)
                          / x[('NominalPeople', '# Zone Occupants')].astype(float),
                          x,
                          area_m_),
            weighted_mean(x[('ZoneHeating', 'Minimum Outdoor Air Flow Rate')].astype(float)
                          / x[('NominalPeople', '# Zone Occupants')].astype(float),
                          x,
                          area_m_))
    return pd.Series(d)


def zone_cop(df):
    """
    Returns the heating and cooling COP for each zones. The energyplus SQL result must contain some required meters
    as described bellow.

    Todo:
        * We could check if the meters are included in the IDF file.

    Args:
        df (pandas.DataFrame):

    Returns:


    Notes:

        Output Meters

        Heating

        - Air System Total Heating Energy
        - Heating:Electricity
        - Heating:Gas
        - Heating:DistrictHeating

        Cooling

        - Air System Total Cooling Energy
        - Cooling:Electricity
        - Cooling:Gas
        - Cooling:DistrictCooling

    """
    # Heating Energy
    heating = get_from_reportdata(df).loc[lambda rd: rd.Name == 'Air System Total Heating Energy'].reset_index()
    heating_out_sys = heating.groupby(['Archetype', 'KeyValue']).sum()['Value']
    heating_out = heating.groupby(['Archetype']).sum()['Value']
    nu_heating = heating_out_sys / heating_out
    heating_in = get_from_reportdata(df).loc[(lambda rd: ((rd.Name == 'Heating:Electricity') |
                                                          (rd.Name == 'Heating:Gas') |
                                                          (rd.Name == 'Heating:DistrictHeating'))),
                                             ['Archetype', 'Value']].set_index('Archetype').sum(level='Archetype')[
        'Value']

    # Cooling Energy
    cooling = get_from_reportdata(df).loc[lambda rd: rd.Name == 'Air System Total Cooling Energy'].reset_index()
    cooling_out_sys = cooling.groupby(['Archetype', 'KeyValue']).sum()['Value']
    cooling_out = cooling.groupby(['Archetype']).sum()['Value']
    nu_cooling = cooling_out_sys / cooling_out
    cooling_in = get_from_reportdata(df).loc[(lambda rd: ((rd.Name == 'Cooling:Electricity') |
                                                          (rd.Name == 'Cooling:Gas') |
                                                          (rd.Name == 'Cooling:DistrictCooling'))),
                                             ['Archetype', 'Value']].set_index('Archetype').sum(level='Archetype')[
        'Value']

    d = {'Heating': heating_out_sys / (nu_heating * heating_in),
         'Cooling': cooling_out_sys / (nu_cooling * cooling_in)}

    # Zone to system correspondence
    df = get_from_tabulardata(df).loc[((lambda e: e.ReportName == 'Standard62.1Summary') and
                                       (lambda e: e.TableName == 'System Ventilation Parameters') and
                                       (lambda e: e.ColumnName == 'AirLoop Name')), ['RowName', 'Value']].reset_index()
    df.rename(columns={'RowName': 'Zone Name', 'Value': 'System Name'}, inplace=True)
    df.loc[:, 'COP Heating'] = df.join(d['Heating'], on=['Archetype', 'System Name'])['Value']
    df.loc[:, 'COP Cooling'] = df.join(d['Cooling'], on=['Archetype', 'System Name'])['Value']
    df.drop(columns='Index', inplace=True)
    return df.groupby(['Archetype', 'Zone Name']).mean()


def zone_setpoint(df):
    """
    Since we can't have a schedule setpoint in Umi, we return the "Design Day" 'Thermostat Setpoint Temperature at
    'Peak Load'

    Args:
        df (pandas.DataFrame): df

    Returns:
        DataFrame of Zone Setpoints for Cooling and Heating
    """
    df = get_from_tabulardata(df)
    tbstr_cooling = df[(df.ReportName == 'HVACSizingSummary') &
                       (df.TableName == 'Zone Sensible Cooling')].reset_index()
    tbpiv_cooling = tbstr_cooling.pivot_table(index=['Archetype', 'RowName'],
                                              columns='ColumnName',
                                              values='Value',
                                              aggfunc=lambda x: ' '.join(x)).replace({'N/A': np.nan}).apply(
        lambda x: pd.to_numeric(x, errors='ignore'))
    tbstr_heating = df[(df.ReportName == 'HVACSizingSummary') &
                       (df.TableName == 'Zone Sensible Heating')].reset_index()
    tbpiv_heating = tbstr_heating.pivot_table(index=['Archetype', 'RowName'],
                                              columns='ColumnName',
                                              values='Value',
                                              aggfunc=lambda x: ' '.join(x)).replace({'N/A': np.nan}).apply(
        lambda x: pd.to_numeric(x, errors='ignore'))
    cd = pd.concat([tbpiv_cooling, tbpiv_heating], keys=['cooling', 'heating'], axis=1)
    cd.index.names = ['Archetype', 'Zone Name']
    return cd


def zone_conditioning(df):
    """
    Aggregation of zone conditioning parameters. Imports Zones, NominalPeople, COP, ZoneCooling and ZoneHeating.

    :param df:
    :return:

    Examples:
        .. doctest:: *

            # >>> df = pu.run_eplus([./examples/zoneuncontrolled.idf], output_report='sql')
            # >>> zone_conditioning(df)

    """
    # Loading each section in a dictionnary. Used to create a new DF using pd.concat()
    d = {'Zones': zone_information(df).reset_index().set_index(['Archetype', 'Zone Name']),
         'NominalPeople': nominal_people(df).reset_index().set_index(['Archetype', 'Zone Name']),
         'COP': zone_cop(df).reset_index().set_index(['Archetype', 'Zone Name']),
         'ZoneCooling': zone_setpoint(df).loc[:, 'cooling'],
         'ZoneHeating': zone_setpoint(df).loc[:, 'heating']}

    df = (pd.concat(d, axis=1, keys=d.keys())
          .dropna(axis=0, how='all', subset=[('Zones', 'Type')])  # Drop rows that are all nans
          .reset_index(level=1, col_level=1, col_fill='Zones')  # Reset Index level to get Zone Name
          .reset_index().set_index(['Archetype', ('Zones', 'RowName')])
          .rename_axis(['Archetype', 'RowName']))

    df[('Zones', 'Zone Type')] = df.apply(lambda x: iscore(x), axis=1)

    df = df.reset_index().groupby(['Archetype', ('Zones', 'Zone Type')]).apply(
        lambda x: zoneconditioning_aggregation(x.set_index(['Archetype', 'RowName'])))

    return df
