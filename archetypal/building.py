import io
import zipfile

import numpy as np
import requests
from sklearn.preprocessing import MinMaxScaler

from archetypal import nrel_bcl_api_request, log, settings
from archetypal.core import EnergyProfile


def download_bld_window(u_factor, shgc, vis_trans, oauth_key, tolerance=0.05,
                        extension='idf'):
    """

    Args:
        u_factor (float or tuple):
        shgc (float or tuple):
        vis_trans (float or tuple):
        tolerance (float):
        oauth_key (str):
        extension (str): specify the extension of the file to download

    Returns:
        eppy.IDF
    """
    filters = []
    # check if one or multiple values
    if isinstance(u_factor, tuple):
        u_factor_dict = '[{} TO {}]'.format(u_factor[0], u_factor[1])
    else:
        # apply tolerance
        u_factor_dict = '[{} TO {}]'.format(u_factor * (1 - tolerance),
                                            u_factor * (1 + tolerance))
    if isinstance(shgc, tuple):
        shgc_dict = '[{} TO {}]'.format(shgc[0], shgc[1])
    else:
        # apply tolerance
        shgc_dict = '[{} TO {}]'.format(shgc * (1 - tolerance),
                                        shgc * (1 + tolerance))
    if isinstance(vis_trans, tuple):
        vis_trans_dict = '[{} TO {}]'.format(vis_trans[0], vis_trans[1])
    else:
        # apply tolerance
        vis_trans_dict = '[{} TO {}]'.format(vis_trans * (1 - tolerance),
                                             vis_trans * (1 + tolerance))

    data = {'keyword': 'Window',
            'format': 'json',
            'f[]': ['fs_a_Overall_U-factor:{}'.format(u_factor_dict),
                    'fs_a_VLT:{}'.format(
                        vis_trans_dict),
                    'fs_a_SHGC:{}'.format(shgc_dict),
                    'sm_component_type:"Window"'],
            'oauth_consumer_key': oauth_key}
    response = nrel_bcl_api_request(data)

    if response['result']:
        log('found {} possible window component(s) matching '
            'the range {}'.format(len(response['result']), str(data['f[]'])))

    # download components
    uids = []
    for component in response['result']:
        uids.append(component['component']['uid'])
    url = 'https://bcl.nrel.gov/api/component/download?uids={}'.format(','
                                                                       ''.join(
        uids))
    # actual download with get()
    d_response = requests.get(url)

    if d_response.ok:
        # loop through files and extract the ones that match the extension
        # parameter
        with zipfile.ZipFile(io.BytesIO(d_response.content)) as z:
            for info in z.infolist():
                if info.filename.endswith(extension):
                    z.extract(info, path=settings.cache_folder)

    # todo: read the idf somehow

    return response['result']


def create_fake_profile(x=None, y1={}, y2={}, normalize=False,
                        profile_type='undefined', sorted=False,
                        ascending=False, units='J'):
    """Utility that generates a generic EnergyProfile isntance

    Args:
        x (np.ndarray): is a linspace
        y1 (dict): {'A':1, 'f':1/8760, 'phy':1, 's':0.5}
        y2 (dict): {'A':1, 'f':1/24, 'phy':1, 's':0.5}
        ascending (bool): if True, sorts in ascending order. Implies 'sorted'
            is also True
        profile_type (str): name to give the series. eg. 'heating load' or
            'cooling load'
        sorted (bool): id True, series will be sorted.

    Returns:
        EnergyProfile: the EnergyProfile
    """
    if x is None:
        x = np.linspace(0, 8759, 8760)
    A1 = y1.get('A', 1)
    f = y1.get('f', 1 / 8760)
    w = 2 * np.pi * f
    phy = y1.get('phy', 1)
    s = y1.get('s', 0.5)
    y1 = A1 * np.sin(w * x + phy) + s

    A = y2.get('A', A1)
    f = y2.get('f', 1 / 24)
    w = 2 * np.pi * f
    phy = y2.get('phy', 1)
    s = y2.get('s', 0.5)
    y2 = A * np.sin(w * x + phy) + s

    y = y1 + y2
    return EnergyProfile(y, index=x, frequency='1H', units=units,
                         profile_type=profile_type, normalize=normalize,
                         is_sorted=sorted,
                         ascending=ascending)
