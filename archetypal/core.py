import functools
import io
import json
import logging as lg
import os
import time
from collections import OrderedDict
from pprint import pformat

import numpy as np
import pandas as pd
from sklearn import preprocessing

from . import settings, object_from_idf, object_from_idfs, simple_glazing, \
    iscore, weighted_mean, top, run_eplus, \
    load_idf
from .utils import log, label_surface, type_surface, layer_composition, \
    schedule_composition, time2time, \
    year_composition, newrange


class Template:
    """

    """

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
        self.structure_definitions = None
        self.zone_details = None
        self.zone_loads = None
        self.zone_conditioning = None
        self.zones = None
        self.zone_ventilation = None
        self.windows_settings = None
        self.building_templates = None
        self.zone_construction_sets = None
        self.domestic_hot_water_settings = None

        if load:
            self.read()

        self.sql = None

    def read(self):
        # Umi stuff
        self.materials_gas = materials_gas(self.idfs)
        self.materials_glazing = materials_glazing(self.idfs)
        self.materials_glazing = newrange(self.materials_gas,
                                          self.materials_glazing)

        self.materials_opaque = materials_opaque(self.idfs)
        self.materials_opaque = newrange(self.materials_glazing,
                                         self.materials_opaque)

        self.constructions_opaque = constructions_opaque(self.idfs,
                                                         self.materials_opaque)
        self.constructions_opaque = newrange(self.materials_opaque,
                                             self.constructions_opaque)

        self.constructions_windows = constructions_windows(self.idfs,
                                                           self.materials_glazing)
        self.constructions_windows = newrange(self.constructions_opaque,
                                              self.constructions_windows)

        self.structure_definitions = structure_definition(self.idfs)
        self.structure_definitions = newrange(self.constructions_windows,
                                              self.structure_definitions)

        self.day_schedules = day_schedules(self.idfs)
        self.day_schedules = newrange(self.structure_definitions,
                                      self.day_schedules)

        self.week_schedules = week_schedules(self.idfs, self.day_schedules)
        self.week_schedules = newrange(self.day_schedules,
                                       self.week_schedules)

        self.year_schedules = year_schedules(self.idfs, self.week_schedules)
        self.year_schedules = newrange(self.week_schedules,
                                       self.year_schedules)

    def run_eplus(self, silent=True, **kwargs):
        """wrapper for :func:`run_eplus` function

        """
        self.sql = run_eplus(self.idf_files, self.weather, output_report='sql',
                             **kwargs)
        if not silent:
            return self.sql

    def to_json(self, path_or_buf=None, orient=None, indent=2,
                date_format=None):
        """Writes the umi template to json format"""

        # from pandas.io import json
        categories = [self.materials_gas,
                      self.materials_glazing,
                      self.materials_opaque,
                      self.constructions_opaque,
                      self.constructions_windows,
                      self.structure_definitions,
                      self.day_schedules,
                      self.week_schedules,
                      self.year_schedules,
                      self.domestic_hot_water_settings,
                      self.zone_ventilation,
                      self.zone_conditioning,
                      self.zone_construction_sets,
                      self.zone_loads,
                      self.zones,
                      self.building_templates,
                      self.windows_settings]
        if not path_or_buf:
            path_or_buf = os.path.join(settings.data_folder, 'temp.json')
            # create the folder on the disk if it doesn't already exist
            if not os.path.exists(settings.data_folder):
                os.makedirs(settings.data_folder)
        with io.open(path_or_buf, 'w', encoding='utf-8') as path_or_buf:
            data_dict = OrderedDict()
            for js in categories:
                if isinstance(js, pd.DataFrame):
                    if not js.columns.is_unique:
                        raise ValueError('columns {} are not unique'.format(
                            js.columns))
                    else:
                        # Firs keep only required columns
                        cols = settings.common_umi_objects[js.name].copy()
                        reset_index_cols_ = js.reset_index()[cols]
                        # Than convert ints to strings. this is how umi needs
                        # them
                        reset_index_cols_['$id'] = reset_index_cols_[
                            '$id'].apply(str)
                        # transform to json and add to dict of objects
                        data_dict[js.name] = json.loads(
                            reset_index_cols_.to_json(orient=orient,
                                                      date_format=date_format),
                            object_pairs_hook=OrderedDict)
                else:
                    # do something with objects that are not DataFrames
                    pass
            # Write the dict to json using json.dumps
            path_or_buf.write(json.dumps(data_dict, indent=indent))


class EnergyProfile(pd.Series):

    @property
    def _constructor(self):
        return EnergyProfile._internal_ctor

    _metadata = ['profile_type', 'base_year', 'frequency', 'is_sorted',
                 'units', 'archetypes']

    @classmethod
    def _internal_ctor(cls, *args, **kwargs):
        # List required arguments here
        kwargs['profile_type'] = None
        kwargs['frequency'] = None
        kwargs['units'] = None
        return cls(*args, **kwargs)

    def __init__(self, data, frequency, units, profile_type='undefinded',
                 index=None, dtype=None, copy=True, name=None,
                 fastpath=False, base_year=2017, normalize=False,
                 is_sorted=False, ascending=False, archetypes=None):
        super(EnergyProfile, self).__init__(data=data, index=index,
                                            dtype=dtype, name=name,
                                            copy=copy, fastpath=fastpath)
        self.profile_type = profile_type
        self.frequency = frequency
        self.base_year = base_year
        self.units = units
        self.archetypes = archetypes
        # handle sorting of the data
        if is_sorted:
            self.is_sorted = True
            self.sort_values(ascending=ascending, inplace=True)
        else:
            self.is_sorted = False

        # handle archetype names
        if isinstance(self.index, pd.MultiIndex):
            self.archetypes = list(set(self.index.get_level_values(level=1)))
        else:
            self.archetypes = None

        # handle normalization
        if normalize:
            self.normalize()

    def normalize(self):
        scaler = preprocessing.MinMaxScaler()
        if self.archetypes:
            self.update(pd.concat([scaler(sub.values.reshape(-1, 1)).ravel()
                              for i, sub in self.groupby(level=0)]))
        else:
            self.update(
                pd.Series(scaler.fit_transform(self.values.reshape(-1,
                                                                   1)).ravel()))

    @property
    def p_max(self):
        if isinstance(self.index, pd.MultiIndex):
            return self.groupby(level=0).max()
        else:
            return self.max()

    @property
    def monthly(self):
        if isinstance(self.index, pd.MultiIndex):
            return self.groupby(level=0).max()
        else:
            datetimeindex = pd.DatetimeIndex(freq=self.frequency,
                                             start='{}-01-01'.format(
                                                 self.base_year),
                                             periods=self.size)
            self_copy = self.copy()
            self_copy.index = datetimeindex
            self_copy = self_copy.resample('M', how='mean')
            self_copy.frequency = 'M'
            return EnergyProfile(self_copy, frequency='M', units=self.units)


class ReportData(pd.DataFrame):
    """This class serves as a subclass of a pandas DataFrame allowing to add
    additional functionnality"""

    ARCHETYPE = 'Archetype'
    REPORTDATAINDEX = 'ReportDataIndex'
    TIMEINDEX = 'TimeIndex'
    REPORTDATADICTIONARYINDEX = 'ReportDataDictionaryIndex'
    VALUE = 'Value'
    ISMETER = 'IsMeter'
    TYPE = 'Type'
    INDEXGROUP = 'IndexGroup'
    TIMESTEPTYPE = 'TimestepType'
    KEYVALUE = 'KeyValue'
    NAME = 'Name'
    REPORTINGFREQUENCY = 'ReportingFrequency'
    SCHEDULENAME = 'ScheduleName'
    UNITS = 'Units'

    @property
    def _constructor(self):
        return ReportData

    @property
    def schedules(self):
        return self.sorted_values(key_value='Schedule Value')

    def heating_load(self, normalized=False, sort=False, ascending=False):
        """Returns the aggragated 'Heating:Electricity', 'Heating:Gas' and
        'Heating:DistrictHeating' of each archetype

        Args:
            normalized (bool): if True, returns a normalized Series.
                Normalization is done with respect to each Archetype
            sort (bool): if True, sorts the values. Usefull when a load
                duration curve is needed.
            ascending (bool): if True, sorts value in ascending order. If a
                Load Duration Curve is needed, use ascending=False.

        Returns:
            pd.Series: the Value series of the Heating Load with a Archetype,
                TimeIndex as MultiIndex.
        """
        from sklearn import preprocessing
        hl = self.filter_report_data(name=('Heating:Electricity',
                                           'Heating:Gas',
                                           'Heating:DistrictHeating')).groupby(
            ['Archetype', 'TimeIndex']).sum(level='TimeIndex')
        units = set(hl.Units)
        hl = hl.Value
        if sort:
            hl = hl.sort_values(ascending=ascending)
        if normalized:
            # for each archetype use the min_max_scaler and concatenate back
            # into a Series
            min_max_scaler = preprocessing.MinMaxScaler()
            hl_groups = [pd.Series(min_max_scaler.fit_transform(
                hl.values.reshape(-1, 1)).ravel(), index=hl.index) for i, hl in
                         hl.groupby(level='Archetype')]
            hl = pd.concat(hl_groups)
        log('Returned Heating Load in units of {}'.format(str(units)), lg.DEBUG)
        return hl

    def filter_report_data(self, archetype=None, reportdataindex=None,
                           timeindex=None, reportdatadictionaryindex=None,
                           value=None, ismeter=None, type=None,
                           indexgroup=None, timesteptype=None, keyvalue=None,
                           name=None, reportingfrequency=None,
                           schedulename=None, units=None, inplace=False):
        """filter RaportData using specific keywords. Each keywords can be a
        tuple of strings (str1, str2, str3) which will return the logical_or
        on the specific column.

        Args:
            archetype (str or tuple):
            reportdataindex (str or tuple):
            timeindex (str or tuple):
            reportdatadictionaryindex (str or tuple):
            value (str or tuple):
            ismeter (str or tuple):
            type (str or tuple):
            indexgroup (str or tuple):
            timesteptype (str or tuple):
            keyvalue (str or tuple):
            name (str or tuple):
            reportingfrequency (str or tuple):
            schedulename (str or tuple):
            units (str or tuple):
            inplace (str or tuple):

        Returns:
            pandas.DataFrame
        """
        start_time = time.time()
        c_n = []

        if archetype:
            c_1 = conjunction(*[self[self.ARCHETYPE] ==
                                archetype for
                                archetype in
                                archetype], logical=np.logical_or) \
                if isinstance(archetype, tuple) \
                else self[self.ARCHETYPE] == archetype
            c_n.append(c_1)
        if reportdataindex:
            c_2 = conjunction(*[self[self.REPORTDATAINDEX] ==
                                reportdataindex for
                                reportdataindex in
                                reportdataindex],
                              logical=np.logical_or) \
                if isinstance(reportdataindex, tuple) \
                else self[self.REPORTDATAINDEX] == reportdataindex
            c_n.append(c_2)
        if timeindex:
            c_3 = conjunction(*[self[self.TIMEINDEX] ==
                                timeindex for
                                timeindex in
                                timeindex],
                              logical=np.logical_or) \
                if isinstance(timeindex, tuple) \
                else self[self.TIMEINDEX] == timeindex
            c_n.append(c_3)
        if reportdatadictionaryindex:
            c_4 = conjunction(*[self[self.REPORTDATADICTIONARYINDEX] ==
                                reportdatadictionaryindex for
                                reportdatadictionaryindex in
                                reportdatadictionaryindex],
                              logical=np.logical_or) \
                if isinstance(reportdatadictionaryindex, tuple) \
                else self[self.REPORTDATADICTIONARYINDEX] == \
                     reportdatadictionaryindex
            c_n.append(c_4)
        if value:
            c_5 = conjunction(*[self[self.VALUE] ==
                                value for
                                value in
                                value], logical=np.logical_or) \
                if isinstance(value, tuple) \
                else self[self.VALUE] == value
            c_n.append(c_5)
        if ismeter:
            c_6 = conjunction(*[self[self.ISMETER] ==
                                ismeter for
                                ismeter in
                                ismeter],
                              logical=np.logical_or) \
                if isinstance(ismeter, tuple) \
                else self[self.ISMETER] == ismeter
            c_n.append(c_6)
        if type:
            c_7 = conjunction(*[self[self.TYPE] ==
                                type for
                                type in
                                type],
                              logical=np.logical_or) \
                if isinstance(type, tuple) \
                else self[self.TYPE] == type
            c_n.append(c_7)
        if indexgroup:
            c_8 = conjunction(*[self[self.INDEXGROUP] ==
                                indexgroup for
                                indexgroup in
                                indexgroup],
                              logical=np.logical_or) \
                if isinstance(indexgroup, tuple) \
                else self[self.INDEXGROUP] == indexgroup
            c_n.append(c_8)
        if timesteptype:
            c_9 = conjunction(*[self[self.TIMESTEPTYPE] ==
                                timesteptype for
                                timesteptype in
                                timesteptype],
                              logical=np.logical_or) \
                if isinstance(timesteptype, tuple) \
                else self[self.TIMESTEPTYPE] == timesteptype
            c_n.append(c_9)
        if keyvalue:
            c_10 = conjunction(*[self[self.KEYVALUE] ==
                                 keyvalue for
                                 keyvalue in
                                 keyvalue],
                               logical=np.logical_or) \
                if isinstance(keyvalue, tuple) \
                else self[self.KEYVALUE] == keyvalue
            c_n.append(c_10)
        if name:
            c_11 = conjunction(*[self[self.NAME] ==
                                 name for
                                 name in
                                 name],
                               logical=np.logical_or) \
                if isinstance(name, tuple) \
                else self[self.NAME] == name
            c_n.append(c_11)
        if reportingfrequency:
            c_12 = conjunction(*[self[self.REPORTINGFREQUENCY] ==
                                 reportingfrequency for
                                 reportingfrequency in
                                 reportingfrequency],
                               logical=np.logical_or) \
                if isinstance(reportingfrequency, tuple) \
                else self[self.REPORTINGFREQUENCY] == reportingfrequency
            c_n.append(c_12)
        if schedulename:
            c_13 = conjunction(*[self[self.SCHEDULENAME] ==
                                 schedulename for
                                 schedulename in
                                 schedulename],
                               logical=np.logical_or) \
                if isinstance(schedulename, tuple) \
                else self[self.SCHEDULENAME] == schedulename
            c_n.append(c_13)
        if units:
            c_14 = conjunction(*[self[self.UNITS] ==
                                 units for
                                 units in
                                 units], logical=np.logical_or) \
                if isinstance(units, tuple) \
                else self[self.UNITS] == units
            c_n.append(c_14)

        filtered_df = self.loc[conjunction(*c_n, logical=np.logical_and)]
        log('filtered DataFrame in {:,.2f} seconds'.format(
            time.time() - start_time))
        if inplace:
            return filtered_df._update_inplace(filtered_df)
        else:
            return filtered_df._constructor(filtered_df).__finalize__(
                filtered_df)

    def sorted_values(self, key_value=None, name=None,
                      by='TimeIndex', ascending=True):
        """Returns sorted values by filtering key_value and name

        Args:
            self: The ReporatData DataFrame
            key_value (str): key_value column filter
            name (str): name column filter
            by (str): sorting by this column name
            ascending (bool):

        Returns:
            ReportData
        """
        if key_value and name:
            return self.filter_report_data(name=name,
                                           keyvalue=key_value).sort_values(
                by=by, ascending=ascending).reset_index(drop=True).rename_axis(
                'TimeStep').set_index([
                'Archetype'], append=True).swaplevel(i=-2, j=-1, axis=0)
        else:
            return self.sort_values(by=by, inplace=False)


def conjunction(*conditions, logical=np.logical_and):
    """Applies a logical function on n conditons"""
    return functools.reduce(logical, conditions)


def or_conjunction(*conditions):
    return functools.reduce(np.logical_or, conditions)


def mean_profile(df: ReportData):
    """calculates"""
    return df[df.SCORES].mean()


def convert_necb_to_umi_json(idfs, idfobjects=None):
    # if no list of idfobjects:
    if idfobjects is None:
        idfobjects = settings.useful_idf_objects

    for idf, idfobject in zip(idfs, idfobjects):
        print(object_from_idf(idf, idfobject))


def gas_type(row):
    """Return the UMI gas type number

    Args:
        row (pandas.DataFrame):name

    Returns:
        int: UMI gas type number. The return number is specific to the umi api.

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
    cols = settings.common_umi_objects['GasMaterials'].copy()

    # Add Type of gas column
    materials_df['Type'] = 'Gas'
    materials_df['GasType'] = materials_df.apply(lambda x: gas_type(x), axis=1)
    materials_df['Cost'] = 0
    materials_df['EmbodiedCarbon'] = 0
    materials_df['EmbodiedCarbonStdDev'] = 0
    materials_df['EmbodiedEnergy'] = 0
    materials_df['EmbodiedEnergyStdDev'] = 0
    materials_df[
        'SubstitutionRatePattern'] = np.NaN  # ! Might have to change to an
    # empty array
    materials_df['SubstitutionTimestep'] = 0
    materials_df['TransportCarbon'] = 0
    materials_df['TransportDistance'] = 0
    materials_df['TransportEnergy'] = 0
    materials_df[
        'Life'] = 1  # TODO: What does Life mean? Always 1 in Boston Template
    materials_df['Comment'] = ''
    try:
        materials_df['DataSource'] = materials_df['Archetype']
    except Exception as e:
        log('An exception was raised while setting the DataSource of the '
            'objects',
            lg.WARNING)
        log('{}'.format(e), lg.ERROR)
        log('Falling back onto first IDF file containing this common object',
            lg.WARNING)
        materials_df['DataSource'] = 'First IDF file containing ' \
                                     'this common object'

    materials_df = materials_df.reset_index(drop=True).rename_axis(
        '$id').reset_index()
    log('Returning {} WINDOWMATERIAL:GAS objects in a DataFrame'.format(
        len(materials_df)))
    materials_df = materials_df[cols].set_index(
        '$id')  # Keep only relevant columns
    materials_df.name = 'GasMaterials'
    materials_df.index += 1  # Shift index by one since umi is one-based indexed
    return materials_df


def materials_glazing(idfs):
    """Material Glazing group

    Args:
        idfs (list or dict): parsed IDF files

    Returns:
        padnas.DataFrame: Returns a DataFrame with the all necessary Umi columns
    """
    origin_time = time.time()
    log('Initiating materials_glazing...')
    materials_df = object_from_idfs(idfs, 'WINDOWMATERIAL:GLAZING',
                                    first_occurrence_only=False)
    cols = settings.common_umi_objects['GlazingMaterials'].copy()
    cols.pop(0)  # remove $id
    cols.append('Thickness')
    cols.append('Archetype')
    column_rename = {'Optical_Data_Type': 'Optical',
                     'Window_Glass_Spectral_Data_Set_Name': 'OpticalData',
                     'Solar_Transmittance_at_Normal_Incidence':
                         'SolarTransmittance',
                     'Front_Side_Solar_Reflectance_at_Normal_Incidence':
                         'SolarReflectanceFront',
                     'Back_Side_Solar_Reflectance_at_Normal_Incidence':
                         'SolarReflectanceBack',
                     'Infrared_Transmittance_at_Normal_Incidence':
                         'IRTransmittance',
                     'Visible_Transmittance_at_Normal_Incidence':
                         'VisibleTransmittance',
                     'Front_Side_Visible_Reflectance_at_Normal_Incidence':
                         'VisibleReflectanceFront',
                     'Back_Side_Visible_Reflectance_at_Normal_Incidence':
                         'VisibleReflectanceBack',
                     'Front_Side_Infrared_Hemispherical_Emissivity':
                         'IREmissivityFront',
                     'Back_Side_Infrared_Hemispherical_Emissivity':
                         'IREmissivityBack',
                     'Dirt_Correction_Factor_for_Solar_and_Visible_Transmittance':
                         'DirtFactor'}
    # materials_df = materials_df.loc[materials_df.MaterialType == 10]
    materials_df = materials_df.rename(columns=column_rename)
    materials_df = materials_df.reindex(columns=cols)
    materials_df = materials_df.fillna({'DirtFactor': 1.0})
    materials_df['Comment'] = 'default'
    materials_df['Cost'] = 0
    try:
        materials_df['DataSource'] = materials_df['Archetype']
    except Exception as e:
        log('An exception was raised while setting the DataSource of the '
            'objects',
            lg.WARNING)
        log('{}'.format(e), lg.ERROR)
        log('Falling back onto first IDF file containing this common object',
            lg.WARNING)
        materials_df['DataSource'] = 'First IDF file containing this ' \
                                     'common object'

    materials_df['Density'] = 2500
    materials_df['EmbodiedCarbon'] = 0
    materials_df['EmbodiedCarbonStdDev'] = 0
    materials_df['EmbodiedEnergy'] = 0
    materials_df['EmbodiedEnergyStdDev'] = 0
    materials_df['Life'] = 1
    materials_df[
        'SubstitutionRatePattern'] = np.NaN  # TODO: ! Might have to change
    # to an empty array
    materials_df['SubstitutionTimestep'] = 0
    materials_df['TransportCarbon'] = 0
    materials_df['TransportDistance'] = 0
    materials_df['TransportEnergy'] = 0
    materials_df['Type'] = 'Uncoated'  # TODO Further investigation necessary

    materials_df = materials_df.reset_index(drop=True).rename_axis('$id')

    # Now, we create glazing materials using the
    # 'WINDOWMATERIAL:SIMPLEGLAZINGSYSTEM' objects and append them to the
    # list.
    # Trying to get simple_glazing_systems
    sgs = get_simple_glazing_system(idfs)
    if not sgs.empty:
        log('Appending to WINDOWMATERIAL:GLAZING DataFrame...')
        materials_df = materials_df.append(sgs, ignore_index=True,
                                           sort=True).reset_index(
            drop=True).rename_axis('$id')
    # Return the Dataframe
    log('Returning {} WINDOWMATERIAL:GLAZING objects in a DataFrame'.format(
        len(materials_df)))
    log('Completed materials_glazing in {:,.2f} seconds\n'.format(
        time.time() - origin_time))
    materials_df = materials_df[cols]
    materials_df.name = 'GlazingMaterials'
    return materials_df


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
        lambda x: x['Thickness'] / x['Conductivity'] if ~np.isnan(
            x['Conductivity']) else
        x['ThermalResistance'], axis=1)

    # Fill nan values (nomass materials) with defaults
    materials_df = materials_df.fillna(
        {'Thickness': 0.0127,  # half inch tichness
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
        log(
            'An exception was raised while setting the DataSource of the '
            'objects',
            lg.WARNING)
        log('{}'.format(e), lg.ERROR)
        log('Falling back onto first IDF file containing this common object',
            lg.WARNING)
        materials_df[
            'DataSource'] = 'First IDF file containing this common object'

    materials_df['EmbodiedCarbon'] = 0
    materials_df['EmbodiedCarbonStdDev'] = 0
    materials_df['EmbodiedEnergy'] = 0
    materials_df['EmbodiedEnergyStdDev'] = 0
    materials_df['Life'] = 1
    materials_df['MoistureDiffusionResistance'] = 50
    materials_df['PhaseChange'] = False
    materials_df['PhaseChangeProperties'] = ''
    # TODO: Further investigation needed
    materials_df['SubstitutionRatePattern'] = np.NaN
    # TODO: Might have to change to an empty array
    materials_df['SubstitutionTimestep'] = 0
    materials_df['TransportCarbon'] = 0
    materials_df['TransportDistance'] = 0
    materials_df['TransportEnergy'] = 0
    materials_df['Type'] = ''  # TODO: Further investigation necessary
    materials_df['VariableConductivity'] = False
    materials_df['VariableConductivityProperties'] = np.NaN
    # TODO: Further investigation necessary

    materials_df = materials_df.reset_index(drop=True).rename_axis('$id')
    log('Completed materials_opaque in {:,.2f} seconds\n'.format(
        time.time() - origin_time))
    materials_df = materials_df[cols]
    materials_df.name = 'OpaqueMaterials'
    return materials_df


def constructions_opaque(idfs, opaquematerials=None):
    """Opaque Construction group

    Args:
        idfs (list or dict): parsed IDF files opaquematerials
            (pandas.DataFrame): DataFrame generated by
            :func:`materials_opaque()`

    Returns:
        padnas.DataFrame: Returns a DataFrame with the all necessary Umi columns

    """
    origin_time = time.time()
    log('Initiating constructions_opaque...')
    constructions_df = object_from_idfs(idfs, 'CONSTRUCTION',
                                        first_occurrence_only=False)
    bldg_surface_detailed = object_from_idfs(idfs, 'BUILDINGSURFACE:DETAILED',
                                             first_occurrence_only=False)

    log('Joining constructions_df on bldg_surface_detailed...')
    constructions_df = bldg_surface_detailed.join(
        constructions_df.set_index(['Archetype', 'Name']),
        on=['Archetype', 'Construction_Name'], rsuffix='_constructions')

    constructions_df['Category'] = constructions_df.apply(
        lambda x: label_surface(x), axis=1)
    constructions_df['Type'] = constructions_df.apply(lambda x: type_surface(x),
                                                      axis=1)

    if opaquematerials is not None:
        start_time = time.time()
        log('Initiating constructions_opaque Layer composition...')
        df = pd.DataFrame(constructions_df.set_index(
            ['Archetype', 'Name', 'Construction_Name']).loc[:,
                          constructions_df.set_index(['Archetype', 'Name',
                                                      'Construction_Name']).columns.str.contains(
                              'Layer')].stack(), columns=['Layers']).join(
            opaquematerials.reset_index().set_index(['Archetype', 'Name']),
            on=['Archetype', 'Layers']).loc[:,
             ['$id', 'Thickness']].unstack(level=3).apply(
            lambda x: layer_composition(x), axis=1).rename('Layers')
        constructions_df = constructions_df.join(df, on=['Archetype', 'Name',
                                                         'Construction_Name'])
        log('Completed constructions_df Layer composition in {:,.2f}'
            'seconds'.format(time.time() - start_time))
    else:
        log('Could not create layer_composition because the necessary lookup '
            'DataFrame "OpaqueMaterials"  was '
            'not provided', lg.WARNING)
    cols = settings.common_umi_objects['OpaqueConstructions'].copy()

    constructions_df['AssemblyCarbon'] = 0
    constructions_df['AssemblyCost'] = 0
    constructions_df['AssemblyEnergy'] = 0
    constructions_df['Comments'] = 'default'

    try:
        constructions_df['DataSource'] = constructions_df['Archetype']
    except Exception as e:
        log('An exception was raised while setting the DataSource of the '
            'objects',
            lg.WARNING)
        log('{}'.format(e), lg.ERROR)
        log('Falling back onto first IDF file containing this common object',
            lg.WARNING)
        constructions_df['DataSource'] = 'First IDF file containing ' \
                                         'this common object'

    constructions_df['DisassemblyCarbon'] = 0
    constructions_df['DisassemblyEnergy'] = 0
    constructions_df = constructions_df.rename(
        columns={'Name': 'Zone Name'})
    constructions_df = constructions_df.rename(
        columns={'Construction_Name': 'Name'})
    constructions_df = constructions_df.reset_index(drop=True).rename_axis(
        '$id').reset_index()
    log('Completed constructions_opaque in {:,.2f} seconds\n'.format(
        time.time() - origin_time))
    constructions_df = constructions_df[cols].set_index('$id')
    constructions_df.name = 'OpaqueConstructions'
    return constructions_df


def constructions_windows(idfs, material_glazing=None):
    """Window Construction group

    Args:
        idfs (list or dict): parsed IDF files
        material_glazing (pandas.DataFrame): DataFrame generated by
            :func:`materials_glazing`

    Returns:
        padnas.DataFrame: Returns a DataFrame with the all necessary Umi columns

    """
    origin_time = time.time()
    log('Initiating construction_windows...')
    constructions_df = object_from_idfs(idfs, 'CONSTRUCTION',
                                        first_occurrence_only=False)
    constructions_window_df = object_from_idfs(idfs,
                                               'FENESTRATIONSURFACE:DETAILED',
                                               first_occurrence_only=False)
    constructions_window_df = constructions_window_df.join(
        constructions_df.set_index(['Archetype', 'Name']),
        on=['Archetype', 'Construction_Name'],
        rsuffix='_constructions')
    if material_glazing is not None:
        log('Initiating constructions_windows Layer composition...')
        start_time = time.time()
        df = (pd.DataFrame(constructions_window_df.set_index(
            ['Archetype', 'Name', 'Construction_Name']).loc[:,
                           constructions_window_df.set_index(
                               ['Archetype', 'Name',
                                'Construction_Name']).columns.str.contains(
                               'Layer')].stack(), columns=['Layers']).join(
            material_glazing.reset_index().set_index(['Archetype', 'Name']),
            on=['Archetype', 'Layers']).loc[:, ['$id', 'Thickness']].unstack(
            level=3).apply(lambda x: layer_composition(x), axis=1).rename(
            'Layers'))
        if not df.isna().all():
            constructions_window_df = \
                constructions_window_df.join(df, on=['Archetype',
                                                     'Name',
                                                     'Construction_Name'])
        constructions_window_df.dropna(subset=['Layers'], inplace=True)
        log('Completed constructions_window_df Layer composition in {:,'
            '.2f} seconds'.format(time.time() - start_time))
    else:
        log('Could not create layer_composition because the necessary lookup '
            'DataFrame "OpaqueMaterials"  was '
            'not provided', lg.WARNING)

    constructions_window_df.loc[:, 'AssemblyCarbon'] = 0
    constructions_window_df.loc[:, 'AssemblyCost'] = 0
    constructions_window_df.loc[:, 'AssemblyEnergy'] = 0
    constructions_window_df.loc[:, 'Category'] = 'Single'
    constructions_window_df.loc[:, 'Type'] = 2
    constructions_window_df.loc[:, 'Comments'] = 'default'

    try:
        constructions_window_df['DataSource'] = constructions_window_df[
            'Archetype']
    except Exception as e:
        log('An exception was raised while setting the DataSource of the '
            'objects',
            lg.WARNING)
        log('{}'.format(e), lg.ERROR)
        log('Falling back onto first IDF file containing this common object',
            lg.WARNING)
        constructions_window_df[
            'DataSource'] = 'First IDF file containing this common object'

    constructions_window_df.loc[:, 'DisassemblyCarbon'] = 0
    constructions_window_df.loc[:, 'DisassemblyEnergy'] = 0
    constructions_window_df.rename(columns={'Name': 'Zone Name'},
                                   inplace=True)
    constructions_window_df.rename(columns={'Construction_Name': 'Name'},
                                   inplace=True)
    constructions_window_df = constructions_window_df.reset_index(
        drop=True).rename_axis('$id').reset_index()

    cols = settings.common_umi_objects['WindowConstructions'].copy()
    cols.append('Archetype')
    log('Completed constructions_windows in {:,.2f} seconds\n'.format(
        time.time() - origin_time))
    constructions_window_df = constructions_window_df[cols].set_index('$id')
    constructions_window_df.name = 'WindowConstructions'
    return constructions_window_df


def get_simple_glazing_system(idfs):
    """Retreives all simple glazing objects from a list of IDF files. Calls
    :func:`simple_glazing` in order to calculate a new glazing system that
    has the same properties.

    Args:
        idfs (list or dict): parsed IDF files

    Returns:
        pandas.DataFrame : A DataFrame

    """
    try:
        materials_df = object_from_idfs(idfs,
                                        'WINDOWMATERIAL:SIMPLEGLAZINGSYSTEM',
                                        first_occurrence_only=False)

        materials_with_sg = materials_df.set_index(['Archetype', 'Name']).apply(
            lambda row: simple_glazing(row['Solar_Heat_Gain_Coefficient'],
                                       row['UFactor'],
                                       row['Visible_Transmittance']),
            axis=1).apply(pd.Series)
        materials_umi = materials_with_sg.reset_index()
        materials_umi['Optical'] = 'SpectralAverage'
        materials_umi['OpticalData'] = ''
        materials_umi['DataSource'] = materials_umi.apply(
            lambda row: apply_window_perf(row), axis=1)
        materials_umi['key'] = 'WINDOWMATERIAL:SIMPLEGLAZINGSYSTEM'
    except Exception as e:
        log('Error: {}'.format(e), lg.ERROR)
        return pd.DataFrame([])
        # return empty df since we could not find any simple glazing systems
    else:
        log('Found {} WINDOWMATERIAL:SIMPLEGLAZINGSYSTEM objects'.format(
            len(materials_umi)))
        return materials_umi


def apply_window_perf(row):
    """Returns the string description of the window component"""
    perfs = {'shgc': row['SolarHeatGainCoefficient'],
             'ufactor': row['UFactor'],
             'tvis': row['VisibleTransmittance']}
    for perf in perfs:
        try:
            perfs[perf] = float(perfs[perf])
        except ValueError:
            perfs['tvis'] = row['SolarTransmittance']
    return 'EnergyPlus Simple Glazing Calculation shgc: {:,.2f}, u-value: ' \
           '{:,.2f}, t_vis: {:,.2f}'.format(perfs['shgc'],
                                            perfs['ufactor'],
                                            perfs['tvis'])


def day_schedules(idfs):
    """Parses daily schedules of type 'SCHEDULE:DAY:INTERVAL'

    Args:
        idfs (list or dict): parsed IDF files

    Returns:

    """
    origin_time = time.time()
    log('Initiating day_schedules...')
    schedule = object_from_idfs(idfs, 'SCHEDULE:DAY:INTERVAL',
                                first_occurrence_only=False)
    cols = settings.common_umi_objects['DaySchedules'].copy()
    if not schedule.empty:
        schedule['Values'] = schedule.apply(lambda x: time2time(x), axis=1)

        schedule.loc[:, 'Category'] = 'Day'
        schedule.loc[:, 'Comments'] = 'Comments'
        schedule.loc[:, 'DataSource'] = 'default'
        schedule.loc[:, 'Type'] = schedule['Schedule_Type_Limits_Name']

        schedule = (schedule.reset_index(drop=True)
                    .rename_axis('$id').reset_index())
        cols.append('Archetype')
        log('Completed day_schedules in {:,.2f} seconds\n'.format(
            time.time() - origin_time))
        schedule = schedule[cols].set_index('$id')
        schedule.name = 'DaySchedules'
        return schedule
    else:
        log('Returning Empty DataFrame', lg.WARNING)
        schedule = pd.DataFrame([], columns=cols)
        schedule.name = 'DaySchedules'
        return schedule


def week_schedules(idfs, dayschedules=None):
    """Parses daily schedules of type 'SCHEDULE:WEEK:DAILY'

    Args:
        idfs (list or dict): parsed IDF files
            dayschedules (pandas.DataFrame): DataFrame generated by
            :func:`day_schedules`

    Returns:

    """
    origin_time = time.time()
    log('Initiating week_schedules...')
    schedule = object_from_idfs(idfs, 'SCHEDULE:WEEK:DAILY',
                                first_occurrence_only=False)
    cols = settings.common_umi_objects['WeekSchedules'].copy()
    if not schedule.empty:

        if dayschedules is not None:
            start_time = time.time()
            df = (pd.DataFrame(schedule.set_index(['Archetype', 'Name'])
                               .loc[:, schedule.set_index(['Archetype', 'Name'])
                               .columns.str.contains('Schedule')]
                               .stack(), columns=['Schedule'])
                  .join(dayschedules.reset_index()
                        .set_index(['Archetype', 'Name']),
                        on=['Archetype', 'Schedule'])
                  .loc[:, ['$id', 'Values']]
                  .unstack(level=2)
                  .apply(lambda x: schedule_composition(x),
                         axis=1).rename('Days'))

            schedule = schedule.join(df, on=['Archetype', 'Name'])
            log('Completed week_schedules schedule composition in {:,'
                '.2f} seconds'.format(time.time() - start_time))
        else:
            log('Could not create layer_composition because the necessary '
                'lookup DataFrame "DaySchedules"  was '
                'not provided', lg.WARNING)

        schedule.loc[:, 'Category'] = 'Week'
        schedule.loc[:, 'Comments'] = 'default'
        schedule.loc[:, 'DataSource'] = schedule['Archetype']

        # Copy the Schedule Type Over
        schedule = schedule.join(
            dayschedules.set_index(['Archetype', 'Name']).loc[:, ['Type']],
            on=['Archetype', 'Monday_ScheduleDay_Name'])

        schedule = schedule.reset_index(drop=True).rename_axis(
            '$id').reset_index()
        cols.append('Archetype')
        log('Completed day_schedules in {:,.2f} seconds\n'.format(
            time.time() - origin_time))
        schedule = schedule[cols].set_index('$id')
        schedule.name = 'WeekSchedules'
        return schedule
    else:
        log('Returning Empty DataFrame', lg.WARNING)
        schedule = pd.DataFrame([], columns=cols)
        schedule.name = 'WeekSchedules'
        return schedule


def year_schedules(idfs, weekschedule=None):
    """Parses daily schedules of type 'SCHEDULE:YEAR'

    Args:
        idfs (list or dict): parsed IDF files
            weekschedule (pandas.DataFrame): DataFrame generated by
            :func:`week_schedules`

    Returns:

    """
    origin_time = time.time()
    log('Initiating week_schedules...')
    schedule = object_from_idfs(idfs, 'SCHEDULE:YEAR',
                                first_occurrence_only=False)
    cols = settings.common_umi_objects['YearSchedules'].copy()
    if not schedule.empty:

        if weekschedule is not None:
            start_time = time.time()
            df = (pd.DataFrame(schedule
                               .set_index(['Archetype', 'Name'])
                               .drop(['index',
                                      'key',
                                      'Schedule_Type_Limits_Name'],
                                     axis=1).stack(), columns=['Schedules'])
                  .reset_index().join(weekschedule
                                      .reset_index()
                                      .set_index(['Archetype', 'Name']),
                                      on=['Archetype', 'Schedules'])
                  .set_index(['Archetype', 'Name', 'level_2'])
                  .drop(['Category', 'Comments',
                         'DataSource', 'Days', 'Type'], axis=1)
                  .unstack()
                  .apply(lambda x: year_composition(x), axis=1).rename('Parts'))

            schedule = schedule.join(df, on=['Archetype', 'Name'])
            log('Completed week_schedules schedule composition in {:,.2f} '
                'seconds'.format(time.time() - start_time))
        else:
            log('Could not create layer_composition because the necessary '
                'lookup DataFrame "WeekSchedule"  was '
                'not provided', lg.WARNING)

        schedule['Category'] = 'Year'
        schedule['Comments'] = 'default'
        schedule['DataSource'] = schedule['Archetype']

        schedule = schedule.join(
            weekschedule.set_index(['Archetype', 'Name']).loc[:, ['Type']],
            on=['Archetype', 'ScheduleWeek_Name_1'])

        schedule = schedule.reset_index(drop=True).rename_axis(
            '$id').reset_index()
        cols.append('Archetype')
        log('Completed day_schedules in {:,.2f} seconds\n'.format(
            time.time() - origin_time))
        schedule = schedule[cols].set_index('$id')
        schedule.name = 'YearSchedules'
        return schedule
    else:
        log('Returning Empty DataFrame', lg.WARNING)
        schedule = pd.DataFrame([], columns=cols)
        schedule.name = 'YearSchedules'
        return schedule


def zone_loads(df):
    """Takes the sql reports (as a dict of DataFrames), concatenates all
    relevant 'Initialization Summary' tables and
    applies a series of aggragation functions (weighted means and "top").

    Args:
        df (dict): A dict of pandas.DataFrames

    Returns:
        pandas.DataFrame : A new DataFrame with aggragated values

    """
    # Loading each section in a dictionnary. Used to create a new DF using
    # pd.concat()
    d = {'Zones': zone_information(df).reset_index().set_index(['Archetype',
                                                                'Zone Name']),
         'NominalLighting': nominal_lighting(df).reset_index().set_index(
             ['Archetype', 'Zone Name']),
         'NominalPeople': nominal_people(df).reset_index().set_index(
             ['Archetype', 'Zone Name']),
         'NominalInfiltration': nominal_infiltration(
             df).reset_index().set_index(['Archetype', 'Zone Name']),
         'NominalEquipment': nominal_equipment(df).reset_index().set_index(
             ['Archetype', 'Zone Name'])}

    df = (pd.concat(d, axis=1, keys=d.keys())
          .dropna(axis=0, how='all',
                  subset=[('Zones', 'Type')])  # Drop rows that are all nans
          .reset_index(level=1, col_level=1,
                       col_fill='Zones')  # Reset Index level to get Zone Name
          .reset_index().set_index(['Archetype', ('Zones', 'RowName')])
          .rename_axis(['Archetype', 'RowName']))

    df[('Zones', 'Zone Type')] = df.apply(lambda x: iscore(x), axis=1)

    df = df.reset_index().groupby(['Archetype', ('Zones', 'Zone Type')]).apply(
        lambda x: zoneloads_aggregation(x.set_index(['Archetype', 'RowName'])))
    df.name = 'ZoneLoads'
    return df


def zone_ventilation(df):
    """Takes the sql reports (as a dict of DataFrames), concatenates all
    relevant 'Initialization Summary' tables and
    applies a series of aggragation functions (weighted means and "top").

    Args:
        df (dict): A dict of pandas.DataFrames

    Returns:
        pandas.DataFrame:

    """
    # Loading each section in a dictionnary. Used to create a new DF using
    # pd.concat()

    z_info = zone_information(df).reset_index().set_index(['Archetype',
                                                           'Zone Name'])

    _nom_infil = nominal_infiltration(df)
    nom_infil = (_nom_infil.reset_index().set_index(['Archetype',
                                                     'Zone Name'])
                 if not _nom_infil.empty else None)
    _nom_vent = nominal_ventilation(df)
    nom_vent = (_nom_vent.reset_index().set_index(['Archetype',
                                                   'Zone Name']).loc[
                lambda e: e['Fan Type {Exhaust;Intake;Natural}']
                .str.contains('Natural'), :]
                if not _nom_vent.empty else None)
    _nom_natvent = _nom_vent  # we can reuse _nom_vent
    nom_natvent = (_nom_natvent.reset_index().set_index(['Archetype',
                                                         'Zone Name']).loc[
                   lambda e: ~e['Fan Type {Exhaust;Intake;Natural}']
                   .str.contains('Natural'), :]
                   if not _nom_vent.empty else None)
    d = {'Zones': z_info,
         'NominalInfiltration': nom_infil,
         'NominalScheduledVentilation': nom_vent,
         'NominalNaturalVentilation': nom_natvent}

    df = (pd.concat(d, axis=1, keys=d.keys())
          .dropna(axis=0, how='all',
                  subset=[('Zones', 'Type')])  # Drop rows that are all nans
          .reset_index(level=1, col_level=1,
                       col_fill='Zones')  # Reset Index level to get Zone Name
          .reset_index().set_index(['Archetype', ('Zones', 'RowName')])
          .rename_axis(['Archetype', 'RowName']))

    df[('Zones', 'Zone Type')] = df.apply(lambda x: iscore(x), axis=1)

    df_g = df.reset_index().groupby(['Archetype', ('Zones', 'Zone Type')])
    log('{} groups in zone ventiliation aggregation'.format(len(df_g)))
    log('groups are:\n{}'.format(pformat(df_g.groups, indent=3)))
    df = df_g.apply(lambda x: zoneventilation_aggregation(
        x.set_index(['Archetype', 'RowName'])))

    return df


def zoneloads_aggregation(x):
    """Set of different zoneloads_aggregation (weighted mean and "top") on
    multiple objects, eg. ('NominalLighting',
    'Lights/Floor Area {W/m2}').

    All the DataFrame is passed to each function.

    Returns a Series with a MultiIndex

    Args:
        x (pandas.DataFrame):

    Returns:
        pandas.Series: Series with a MultiIndex

    """
    area_m_ = [('Zones', 'Floor Area {m2}'),
               ('Zones',
                'Zone Multiplier')]  # Floor area and zone_loads multiplier
    d = {('NominalLighting', 'weighted mean'):
             weighted_mean(x[('NominalLighting', 'Lights/Floor Area {W/m2}')],
                           x, area_m_),
         ('NominalLighting', 'top'):
             top(x[('NominalLighting', 'Schedule Name')],
                 x, area_m_),
         ('NominalPeople', 'weighted mean'):
             weighted_mean(
                 x[('NominalPeople', 'People/Floor Area {person/m2}')],
                 x, area_m_),
         ('NominalPeople', 'top'):
             top(x[('NominalPeople', 'Schedule Name')],
                 x, area_m_),
         ('NominalEquipment', 'weighted mean'):
             weighted_mean(
                 x[('NominalEquipment', 'Equipment/Floor Area {W/m2}')],
                 x, area_m_),
         ('NominalEquipment', 'top'):
             top(x[('NominalEquipment', 'Schedule Name')],
                 x, area_m_)
         }

    return pd.Series(d)


def zoneventilation_aggregation(df):
    """Set of different zoneventilation_aggregation (weighted mean and "top")
    on multiple objects,
    eg. ('NominalVentilation', 'ACH - Air Changes per Hour').

    All the DataFrame is passed to each function.

    Returns a Series with a MultiIndex

    Args:
        df (pandas.DataFrame):

    Returns:
        pandas.Series: Series with a MultiIndex

    Todo: infiltration for plenums should not be taken into account

    """
    log('\naggregating zone ventilations '
        'for archetype "{}", zone "{}"'.format(df.index.values[0][0],
                                               df[('Zones',
                                                   'Zone Type')].values[0]))

    area_m_ = [('Zones', 'Floor Area {m2}'),
               ('Zones', 'Zone Multiplier')]  # Floor area and zone_loads
    # multiplier

    ach_ = safe_loc(df, ('NominalInfiltration',
                         'ACH - Air Changes per Hour'))
    infil_schedule_name_ = safe_loc(df, ('NominalInfiltration',
                                         'Schedule Name'))
    changes_per_hour_ = safe_loc(df, ('NominalScheduledVentilation',
                                      'ACH - Air Changes per Hour'))
    vent_schedule_name_ = safe_loc(df, ('NominalScheduledVentilation',
                                        'Schedule Name'))
    vent_min_temp_ = safe_loc(df, ('NominalScheduledVentilation',
                                   'Minimum Indoor Temperature{C}/Schedule'))
    natvent_ach_ = safe_loc(df, ('NominalNaturalVentilation',
                                 'ACH - Air Changes per Hour'))
    natvent_schedule_name_ = safe_loc(df, ('NominalNaturalVentilation',
                                           'Schedule Name'))
    natvent_max_temp_ = safe_loc(df, ('NominalNaturalVentilation',
                                      'Maximum Outdoor Temperature{'
                                      'C}/Schedule'))
    natvent_minoutdoor_temp_ = safe_loc(df, ('NominalNaturalVentilation',
                                             'Minimum Outdoor Temperature{'
                                             'C}/Schedule'))
    natvent_minindoor_temp_ = safe_loc(df, ('NominalNaturalVentilation',
                                            'Minimum Indoor Temperature{'
                                            'C}/Schedule'))
    d = {
        ('Infiltration', 'weighted mean {ACH}'): (
            weighted_mean(ach_, df, area_m_)),
        ('Infiltration', 'Top Schedule Name'): (
            top(infil_schedule_name_, df, area_m_)),
        ('ScheduledVentilation', 'weighted mean {ACH}'): (
            weighted_mean(changes_per_hour_, df, area_m_)),
        ('ScheduledVentilation', 'Top Schedule Name'): (
            top(vent_schedule_name_, df, area_m_)),
        ('ScheduledVentilation', 'Setpoint'): (
            top(vent_min_temp_, df, area_m_)),
        ('NatVent', 'weighted mean {ACH}'): (
            weighted_mean(natvent_ach_, df, area_m_)),
        ('NatVent', 'Top Schedule Name'): (
            top(natvent_schedule_name_, df, area_m_)),
        ('NatVent', 'MaxOutdoorAirTemp'): (
            top(natvent_max_temp_, df, area_m_)),
        ('NatVent', 'MinOutdoorAirTemp'): (
            top(natvent_minoutdoor_temp_, df, area_m_)),
        ('NatVent', 'ZoneTempSetpoint'): (
            top(natvent_minindoor_temp_, df, area_m_))}

    return pd.Series(d)


def safe_loc(x, colnames):
    try:
        ach = x[colnames]
    except KeyError:
        log('No such columns {} in DataFrame'.format(str(colnames)))
        return pd.Series([], name=colnames)
    else:
        return ach


def nominal_lighting(df):
    """Nominal lighting

    Args:
        df:

    Returns:
        df

    References:
        * `NominalLighting Table
        <https://bigladdersoftware.com/epx/docs/8-9/output-details-and
        -examples/eplusout-sql.html#nominallighting-table>`_


    """
    df = get_from_tabulardata(df)
    tbstr = df[(df.ReportName == 'Initialization Summary') &
               (df.TableName == 'Lights Internal Gains Nominal')].reset_index()

    tbpiv = tbstr.pivot_table(index=['Archetype', 'RowName'],
                              columns='ColumnName',
                              values='Value',
                              aggfunc=lambda x: ' '.join(x))
    tbpiv = tbpiv.replace({'N/A': np.nan}).apply(
        lambda x: pd.to_numeric(x, errors='ignore'))
    tbpiv = tbpiv.reset_index().groupby(['Archetype', 'Zone Name']).apply(
        nominal_lighting_aggregation)
    return tbpiv.reset_index().groupby(['Archetype', 'Zone Name']).agg(
        lambda x: pd.to_numeric(x, errors='ignore').sum())


def nominal_people(df):
    """Nominal People

    Args:
        df:

    Returns:
        df

    References:
        * `NominalPeople Table
        <https://bigladdersoftware.com/epx/docs/8-9/output-details-and
        -examples/eplusout-sql.html#nominalpeople-table>`_

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

    Args:
        df:

    Returns:
        df

    References:
        * `NominalElectricEquipment Table
        <https://bigladdersoftware.com/epx/docs/8-9/output-details-and
        -examples/eplusout-sql.html#nominalelectricequipment-table>`_

    """
    df = get_from_tabulardata(df)
    tbstr = df[(df.ReportName == 'Initialization Summary') &
               (df.TableName == 'ElectricEquipment Internal Gains '
                                'Nominal')].reset_index()

    tbpiv = tbstr.pivot_table(index=['Archetype', 'RowName'],
                              columns='ColumnName',
                              values='Value',
                              aggfunc=lambda x: ' '.join(x))
    tbpiv = tbpiv.replace({'N/A': np.nan}).apply(
        lambda x: pd.to_numeric(x, errors='ignore'))
    tbpiv = tbpiv.reset_index().groupby(['Archetype', 'Zone Name']).apply(
        nominal_equipment_aggregation)
    return tbpiv


def nominal_infiltration(df):
    """Nominal Infiltration

    Args:
        df:

    Returns:
        df

    References:
        * `<https://bigladdersoftware.com/epx/docs/8-9/output-details-and
        -examples/eplusout-sql.html#nominalinfiltration-table>`_

    """
    df = get_from_tabulardata(df)
    tbstr = df[(df.ReportName == 'Initialization Summary') &
               (df.TableName == 'ZoneInfiltration Airflow Stats '
                                'Nominal')].reset_index()

    tbpiv = tbstr.pivot_table(index=['Archetype', 'RowName'],
                              columns='ColumnName',
                              values='Value',
                              aggfunc=lambda x: ' '.join(x))
    tbpiv.replace({'N/A': np.nan}, inplace=True)
    return tbpiv.reset_index().groupby(['Archetype', 'Zone Name']).agg(
        lambda x: pd.to_numeric(x, errors='ignore').sum())


def nominal_ventilation(df):
    """Nominal Ventilation

    Args:
        df:

    Returns:
        df

    References:
        * `<https://bigladdersoftware.com/epx/docs/8-9/output-details-and
        -examples/eplusout-sql.html#nominalinfiltration-table>`_

    """
    df = get_from_tabulardata(df)
    report_name = 'Initialization Summary'
    table_name = 'ZoneVentilation Airflow Stats Nominal'
    tbstr = df[(df.ReportName == report_name) &
               (df.TableName == table_name)] \
        .reset_index()
    if tbstr.empty:
        log('Table {} does not exist. '
            'Returning an empty DataFrame'.format(table_name), lg.WARNING)
        return pd.DataFrame([])
    tbpiv = tbstr.pivot_table(index=['Archetype', 'RowName'],
                              columns='ColumnName',
                              values='Value',
                              aggfunc=lambda x: ' '.join(x))

    tbpiv = tbpiv.replace({'N/A': np.nan}).apply(
        lambda x: pd.to_numeric(x, errors='ignore'))
    tbpiv = tbpiv.reset_index().groupby(['Archetype',
                                         'Zone Name',
                                         'Fan Type {Exhaust;Intake;Natural}']) \
        .apply(nominal_ventilation_aggregation)
    return tbpiv
    # .reset_index().groupby(['Archetype', 'Zone Name']).agg(
    # lambda x: pd.to_numeric(x, errors='ignore').sum())


def nominal_lighting_aggregation(x):
    """Aggregates the lighting equipments whithin a single zone_loads name (
    implies
    that .groupby(['Archetype',
    'Zone Name']) is performed before calling this function).

    Args:
        x (pandas.DataFrame): x

    Returns:
        pandas.DataFrame: A DataFrame with at least one entry per (
        'Archetype', 'Zone Name'), aggregated accordingly.

    """
    how_dict = {'# Zone Occupants': x['# Zone Occupants'].sum(),
                'End-Use Category': top(x['End-Use Category'],
                                        x, 'Zone Floor Area {m2}'),
                'Fraction Convected': weighted_mean(x['Fraction Convected'],
                                                    x, 'Lighting Level {W}'),
                'Fraction Radiant': weighted_mean(x['Fraction Radiant'],
                                                  x, 'Lighting Level {W}'),
                'Fraction Replaceable': weighted_mean(x['Fraction Replaceable'],
                                                      x, 'Lighting Level {W}'),
                'Fraction Return Air': weighted_mean(x['Fraction Return Air'],
                                                     x, 'Lighting Level {W}'),
                'Fraction Short Wave': weighted_mean(x['Fraction Short Wave'],
                                                     x, 'Lighting Level {W}'),
                'Lighting Level {W}': x['Lighting Level {W}'].sum(),
                'Lights per person {W/person}': x[
                    'Lights per person {W/person}'].sum(),
                'Lights/Floor Area {W/m2}': x['Lights/Floor Area {W/m2}'].sum(),
                'Name': '+'.join(x['Name']),
                'Nominal Maximum Lighting Level {W}': x[
                    'Nominal Maximum Lighting Level {W}'].sum(),
                'Nominal Minimum Lighting Level {W}': x[
                    'Nominal Minimum Lighting Level {W}'].sum(),
                'Schedule Name': top(x['Schedule Name'], x,
                                     'Lighting Level {W}'),
                # todo: The schedule could be an aggregation by itself
                'Zone Floor Area {m2}': x['Zone Floor Area {m2}'].sum()}

    try:
        df = pd.DataFrame(how_dict, index=range(0, 1))  # range should always be
        # one since we are trying to merge zones
    except Exception as e:
        print('{}'.format(e))
    return df


def nominal_equipment_aggregation(x):
    """Aggregates the equipments whithin a single zone_loads name (implies that
    .groupby(['Archetype', 'Zone Name']) is
    performed before calling this function).

    Args:
        x (pandas.DataFrame): x

    Returns:
        pandas.DataFrame: A DataFrame with at least one entry per
            ('Archetype', 'Zone Name'), aggregated accordingly.

    """
    how_dict = {'# Zone Occupants': x['# Zone Occupants'].sum(),
                'End-Use SubCategory': top(x['End-Use SubCategory'],
                                           x, 'Zone Floor Area {m2}'),
                'Equipment Level {W}': x['Equipment Level {W}'].sum(),
                'Equipment per person {W/person}': x[
                    'Equipment per person {W/person}'].sum(),
                'Equipment/Floor Area {W/m2}': x[
                    'Equipment/Floor Area {W/m2}'].sum(),
                'Fraction Convected': weighted_mean(x['Fraction Convected'],
                                                    x, 'Equipment Level {W}'),
                'Fraction Latent': weighted_mean(x['Fraction Latent'],
                                                 x, 'Equipment Level {W}'),
                'Fraction Lost': weighted_mean(x['Fraction Lost'],
                                               x, 'Equipment Level {W}'),
                'Fraction Radiant': weighted_mean(x['Fraction Radiant'],
                                                  x, 'Equipment Level {W}'),
                'Name': '+'.join(x['Name']),
                'Nominal Maximum Equipment Level {W}': x[
                    'Nominal Maximum Equipment Level {W}'].sum(),
                'Nominal Minimum Equipment Level {W}': x[
                    'Nominal Minimum Equipment Level {W}'].sum(),
                'Schedule Name': top(x['Schedule Name'], x,
                                     'Equipment Level {W}'),
                # todo: The schedule could be an aggregation by itself
                'Zone Floor Area {m2}': x['Zone Floor Area {m2}'].sum()}

    try:
        df = pd.DataFrame(how_dict, index=range(0, 1))  # range should always be
        # one since we are trying to merge zones
    except Exception as e:
        print('{}'.format(e))
    return df


def nominal_ventilation_aggregation(x):
    """Aggregates the ventilations whithin a single zone_loads name (implies
    that
    .groupby(['Archetype', 'Zone Name']) is
    performed before calling this function).

    Args:
        x:

    Returns:
        A DataFrame with at least one entry per ('Archetype', 'Zone Name'),
        aggregated accordingly.
    """
    how_dict = {'Name': top(x['Name'],
                            x, 'Zone Floor Area {m2}'),
                'Schedule Name': top(x['Schedule Name'],
                                     x, 'Zone Floor Area {m2}'),
                'Zone Floor Area {m2}': top(x['Zone Floor Area {m2}'],
                                            x, 'Zone Floor Area {m2}'),
                '# Zone Occupants': top(x['# Zone Occupants'],
                                        x, 'Zone Floor Area {m2}'),
                'Design Volume Flow Rate {m3/s}': weighted_mean(
                    x['Design Volume Flow Rate {m3/s}'],
                    x, 'Zone Floor Area {m2}'),
                'Volume Flow Rate/Floor Area {m3/s/m2}': weighted_mean(
                    x['Volume Flow Rate/Floor Area {m3/s/m2}'],
                    x, 'Zone Floor Area {m2}'),
                'Volume Flow Rate/person Area {m3/s/person}': weighted_mean(
                    x['Volume Flow Rate/person Area {m3/s/person}'],
                    x, 'Zone Floor Area {m2}'),
                'ACH - Air Changes per Hour': weighted_mean(
                    x['ACH - Air Changes per Hour'],
                    x, 'Zone Floor Area {m2}'),
                'Fan Pressure Rise {Pa}': weighted_mean(
                    x['Fan Pressure Rise {Pa}'],
                    x, 'Zone Floor Area {m2}'),
                'Fan Efficiency {}': weighted_mean(x['Fan Efficiency {}'],
                                                   x, 'Zone Floor Area {m2}'),
                'Equation A - Constant Term Coefficient {}': top(
                    x['Equation A - Constant Term Coefficient {}'],
                    x, 'Zone Floor Area {m2}'),
                'Equation B - Temperature Term Coefficient {1/C}': top(
                    x['Equation B - Temperature Term Coefficient {1/C}'],
                    x, 'Zone Floor Area {m2}'),
                'Equation C - Velocity Term Coefficient {s/m}': top(
                    x['Equation C - Velocity Term Coefficient {s/m}'],
                    x, 'Zone Floor Area {m2}'),
                'Equation D - Velocity Squared Term Coefficient {s2/m2}': top(
                    x['Equation D - Velocity Squared Term Coefficient {s2/m2}'],
                    x, 'Zone Floor Area {m2}'),
                'Minimum Indoor Temperature{C}/Schedule': top(
                    x['Minimum Indoor Temperature{C}/Schedule'],
                    x, 'Zone Floor Area {m2}'),
                'Maximum Indoor Temperature{C}/Schedule': top(
                    x['Maximum Indoor Temperature{C}/Schedule'],
                    x, 'Zone Floor Area {m2}'),
                'Delta Temperature{C}/Schedule': top(
                    x['Delta Temperature{C}/Schedule'],
                    x, 'Zone Floor Area {m2}'),
                'Minimum Outdoor Temperature{C}/Schedule': top(
                    x['Minimum Outdoor Temperature{C}/Schedule'],
                    x, 'Zone Floor Area {m2}'),
                'Maximum Outdoor Temperature{C}/Schedule': top(
                    x['Maximum Outdoor Temperature{C}/Schedule'],
                    x, 'Zone Floor Area {m2}'),
                'Maximum WindSpeed{m/s}': top(x['Maximum WindSpeed{m/s}'],
                                              x, 'Zone Floor Area {m2}')}
    try:
        df = pd.DataFrame(how_dict, index=range(0, 1))  # range should always be
        # one since we are trying to merge zones
    except Exception as e:
        print('{}'.format(e))
    else:
        return df


def get_from_tabulardata(results):
    """Returns a DataFrame from the 'TabularDataWithStrings' table. A
    multiindex is returned with names ['Archetype', 'Index']

    Args:
        results:

    Returns:

    """
    tab_data_wstring = pd.concat(
        [value['TabularDataWithStrings'] for value in results.values()],
        keys=results.keys(), names=['Archetype'])
    tab_data_wstring.index.names = ['Archetype', 'Index']  #
    # strip whitespaces
    tab_data_wstring.Value = tab_data_wstring.Value.str.strip()
    tab_data_wstring.RowName = tab_data_wstring.RowName.str.strip()
    return tab_data_wstring


def get_from_reportdata(results):
    """Returns a DataFrame from the 'ReportData' table. A multiindex is
    returned with names ['Archetype', 'Index']

    Args:
        results:

    Returns:

    """
    report_data = pd.concat([value['ReportData'] for value in results.values()],
                            keys=results.keys(), names=['Archetype'])
    report_data['ReportDataDictionaryIndex'] = pd.to_numeric(
        report_data['ReportDataDictionaryIndex'])

    report_data_dict = pd.concat(
        [value['ReportDataDictionary'] for value in results.values()],
        keys=results.keys(), names=['Archetype'])

    return report_data.reset_index().join(report_data_dict,
                                          on=['Archetype',
                                              'ReportDataDictionaryIndex'])


def zone_information(df):
    """Each zone_loads is summarized in a simple set of statements

    Args:
        df:

    Returns:
        df

    References:
        * `<https://bigladdersoftware.com/epx/docs/8-3/output-details-and
        -examples/eplusout.eio.html#zone_loads-information>`_

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
    """Aggregates the zones conditioning parameters whithin a single zone_loads
    name (implies that `.groupby(['Archetype',
    ('Zones', 'Zone Type')])` is performed before calling this function).

    Args:
        x:

    Returns:

    """
    d = {}
    area_m_ = [('Zones', 'Zone Multiplier'), ('Zones', 'Floor Area {m2}')]

    d[('COP Heating', 'weighted mean {}')] = (
        weighted_mean(x[('COP', 'COP Heating')],
                      x, area_m_))

    d[('COP Cooling', 'weighted mean {}')] = (
        weighted_mean(x[('COP', 'COP Cooling')],
                      x, area_m_))

    d[('ZoneCooling', 'designday')] = \
        np.nanmean(x.loc[x[(
            'ZoneCooling', 'Thermostat Setpoint Temperature at Peak Load')] > 0,
                         ('ZoneCooling',
                          'Thermostat Setpoint Temperature at Peak Load')])

    d[('ZoneHeating', 'designday')] = \
        np.nanmean(x.loc[x[(
            'ZoneHeating', 'Thermostat Setpoint Temperature at Peak Load')] > 0,
                         ('ZoneHeating',
                          'Thermostat Setpoint Temperature at Peak Load')])

    d[('MinFreshAirPerArea', 'weighted average {m3/s-m2}')] = \
        max(weighted_mean(
            x[('ZoneCooling', 'Minimum Outdoor Air Flow Rate')].astype(float)
            / x.loc[:, ('Zones', 'Floor Area {m2}')].astype(float),
            x,
            area_m_),
            weighted_mean(
                x[('ZoneHeating', 'Minimum Outdoor Air Flow Rate')].astype(
                    float)
                / x[('Zones', 'Floor Area {m2}')].astype(float),
                x,
                area_m_))

    d[('MinFreshAirPerPerson', 'weighted average {m3/s-person}')] = \
        max(weighted_mean(
            x[('ZoneCooling', 'Minimum Outdoor Air Flow Rate')].astype(float)
            / x[('NominalPeople', '# Zone Occupants')].astype(float),
            x,
            area_m_),
            weighted_mean(
                x[('ZoneHeating', 'Minimum Outdoor Air Flow Rate')].astype(
                    float)
                / x[('NominalPeople', '# Zone Occupants')].astype(float),
                x,
                area_m_))
    return pd.Series(d)


def zone_cop(df):
    """Returns the heating and cooling COP for each zones. The energyplus SQL
    result must contain some required meters as described bellow. Also requires
    a full year simulation.

    Todo:
        * We could check if the meters are included in the IDF file.

    Args:
        df (pandas.DataFrame):

    Returns:


    Notes:

        Mandatory Output Meters

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
    rdf = ReportData(get_from_reportdata(df))
    heating = rdf.filter_report_data(
        name='Air System Total Heating Energy').reset_index()
    # heating = get_from_reportdata(df).loc[
    #     lambda rd: rd.Name == 'Air System Total Heating Energy'].reset_index()
    heating_out_sys = heating.groupby(['Archetype', 'KeyValue']).sum()['Value']
    heating_out = heating.groupby(['Archetype']).sum()['Value']
    nu_heating = heating_out_sys / heating_out
    heating_in = rdf.filter_report_data(name=('Heating:Electricity',
                                              'Heating:Gas',
                                              'Heating:DistrictHeating')) \
        .set_index(['Archetype'], append=True).sum(level='Archetype').Value
    # heating_in = rdf.loc[
    #     (lambda rd: ((rd.Name == 'Heating:Electricity') |
    #                  (rd.Name == 'Heating:Gas') |
    #                  (rd.Name == 'Heating:DistrictHeating'))),
    #     ['Archetype', 'Value']].set_index('Archetype').sum(level='Archetype')[
    #     'Value']

    # Cooling Energy
    cooling = get_from_reportdata(df).loc[
        lambda rd: rd.Name == 'Air System Total Cooling Energy'].reset_index()
    cooling_out_sys = cooling.groupby(['Archetype', 'KeyValue']).sum()['Value']
    cooling_out = cooling.groupby(['Archetype']).sum()['Value']
    nu_cooling = cooling_out_sys / cooling_out
    cooling_in = get_from_reportdata(df).loc[
        (lambda rd: ((rd.Name == 'Cooling:Electricity') |
                     (rd.Name == 'Cooling:Gas') |
                     (rd.Name == 'Cooling:DistrictCooling'))),
        ['Archetype', 'Value']].set_index('Archetype').sum(level='Archetype')[
        'Value']

    d = {'Heating': heating_out_sys / (nu_heating * heating_in),
         'Cooling': cooling_out_sys / (nu_cooling * cooling_in)}

    # Zone to system correspondence
    df = get_from_tabulardata(df).loc[
        ((lambda e: e.ReportName == 'Standard62.1Summary') and
         (lambda e: e.TableName == 'System Ventilation Parameters') and
         (lambda e: e.ColumnName == 'AirLoop Name')), ['RowName',
                                                       'Value']].reset_index()
    df.rename(columns={'RowName': 'Zone Name', 'Value': 'System Name'},
              inplace=True)
    df.loc[:, 'COP Heating'] = \
        df.join(d['Heating'], on=['Archetype', 'System Name'])['Value']
    df.loc[:, 'COP Cooling'] = \
        df.join(d['Cooling'], on=['Archetype', 'System Name'])['Value']
    df.drop(columns='Index', inplace=True)
    return df.groupby(['Archetype', 'Zone Name']).mean()


def zone_setpoint(df):
    """Zone heating and cooling setpoints. Since we can't have a schedule
    setpoint in Umi, we return the "Design Day" 'Thermostat Setpoint Temperature
    at 'Peak Load'

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
                                              aggfunc=lambda x: ' '.join(
                                                  x)).replace(
        {'N/A': np.nan}).apply(
        lambda x: pd.to_numeric(x, errors='ignore'))
    tbstr_heating = df[(df.ReportName == 'HVACSizingSummary') &
                       (df.TableName == 'Zone Sensible Heating')].reset_index()
    tbpiv_heating = tbstr_heating.pivot_table(index=['Archetype', 'RowName'],
                                              columns='ColumnName',
                                              values='Value',
                                              aggfunc=lambda x: ' '.join(
                                                  x)).replace(
        {'N/A': np.nan}).apply(
        lambda x: pd.to_numeric(x, errors='ignore'))
    cd = pd.concat([tbpiv_cooling, tbpiv_heating], keys=['cooling', 'heating'],
                   axis=1)
    cd.index.names = ['Archetype', 'Zone Name']
    return cd


def zone_conditioning(df):
    """Aggregation of zone_loads conditioning parameters. Imports Zones,
    NominalPeople, COP, ZoneCooling and ZoneHeating.

    Args:
        df (pandas.DataFrame): df

    Returns:
        DataFrame of Zone Condition parameters

    Examples:
        .. doctest:: *

            # >>> df = ar.run_eplus([./examples/zoneuncontrolled.idf],
            # >>> output_report='sql')
            # >>> zone_conditioning(df)

    """
    # Loading each section in a dictionnary. Used to create
    # a new DF using pd.concat()
    d = {'Zones': zone_information(df).reset_index().set_index(
        ['Archetype', 'Zone Name']),
        'NominalPeople': nominal_people(df).reset_index().set_index(
            ['Archetype', 'Zone Name']),
        'COP': zone_cop(df).reset_index().set_index(
            ['Archetype', 'Zone Name']),
        'ZoneCooling': zone_setpoint(df).loc[:, 'cooling'],
        'ZoneHeating': zone_setpoint(df).loc[:, 'heating']}

    df = (pd.concat(d, axis=1, keys=d.keys())
          .dropna(axis=0, how='all',
                  subset=[('Zones', 'Type')])  # Drop rows that are all nans
          .reset_index(level=1, col_level=1,
                       col_fill='Zones')  # Reset Index level to get Zone Name
          .reset_index().set_index(['Archetype', ('Zones', 'RowName')])
          .rename_axis(['Archetype', 'RowName']))

    df[('Zones', 'Zone Type')] = df.apply(lambda x: iscore(x), axis=1)

    df = df.reset_index().groupby(['Archetype', ('Zones', 'Zone Type')]).apply(
        lambda x: zoneconditioning_aggregation(
            x.set_index(['Archetype', 'RowName'])))

    return df


def zone_conditioning_umi(df):
    pass


def structure_definition(idf):
    cols = settings.common_umi_objects['StructureDefinitions'].copy()
    structure_definition_df = pd.DataFrame([], columns=cols)
    structure_definition_df.set_index('$id', inplace=True)
    structure_definition_df.name = 'StructureDefinitions'
    return structure_definition_df
