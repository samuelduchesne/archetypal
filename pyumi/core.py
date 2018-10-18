import numpy as np
import pandas as pd

from . import settings, object_from_idf


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


def materials_gas(df):
    materials_df = pd.concat([value['Materials'] for value in df.values()], keys=df.keys())
    materials_df = materials_df.rename_axis(['Archetype', 'Index']).reset_index().rename_axis('$id')
    cols = settings.common_umi_objects['GasMaterials']
    try:
        materials_df = materials_df.loc[materials_df.MaterialType == 4]

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
        materials_df['DataSource'] = materials_df.pop('Archetype')

        materials_df = materials_df.reset_index(drop=True).rename_axis('$id').reset_index()

        return materials_df[cols]  # Keep only relevant columns
    except:
        "Column 'MaterialType' not in DataFrame"


def materials_glazing(df):
    materials_df = pd.concat([value['Materials'] for value in df.values()], keys=df.keys())
    materials_df = materials_df.rename_axis(['Archetype', 'Index']).reset_index().rename_axis('$id')
    cols = settings.common_umi_objects['GlazingMaterials']

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

    materials_df = materials_df.loc[materials_df.MaterialType == 10]
    materials_df.rename(columns=column_rename, inplace=True)
    materials_df['Comment'] = 'default'
    materials_df['Cost'] = 0
    materials_df['DataSource'] = materials_df.pop('Archetype')
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

    return materials_df[cols]