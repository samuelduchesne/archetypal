import pandas as pd


def parse_idfs(idf_list, ep_object, keys=None, groupby_name=True):
    """

    :param groupby_name:
    :param idf_list: List of idf files relative or absolute path
    :param ep_object: EnergyPlus object eg. 'WINDOWMATERIAL:GAS'
    :param keys: List of names for each idf file. Becomes level-0 of a multiindex.
    :return: DataFrame of all specifed objects in idf files
    """
    container = []
    for idf in idf_list:
        this_frame = idf.idfobjects[ep_object]
        this_frame = [get_values(frame) for frame in this_frame]
        this_frame = pd.concat(this_frame, ignore_index=True, sort=True)
        container.append(this_frame)
    if keys:
        this_frame = pd.concat(container, keys=keys, names=['Archetype', '$id'], sort=True)
        this_frame.reset_index(inplace=True)
        this_frame.drop(columns='$id', inplace=True)
    if groupby_name:
        this_frame = this_frame.groupby('Name').first()
    this_frame.reset_index(inplace=True)
    this_frame.index.rename('$id', inplace=True)
    return this_frame


def get_values(frame):
    ncols = min(len(frame.fieldvalues), len(frame.fieldnames))
    return pd.DataFrame([frame.fieldvalues[0:ncols]], columns=frame.fieldnames[0:ncols])
