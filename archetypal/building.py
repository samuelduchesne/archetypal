import io
import zipfile

import requests

from archetypal import nrel_bcl_api_request, log, settings


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
