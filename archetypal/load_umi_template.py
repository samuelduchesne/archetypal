import os, json

from pandas.io.json import json_normalize  # package for flattening json in pandas df


def load_umi_template(json_template):
    """

    Args:
        json_template: Absolute or relative filepath to an umi json_template file.

    Returns:
        pandas.DataFrame: 17 DataFrames, one for each component groups

    """
    if os.path.isfile(json_template):
        with open(json_template) as f:
            dicts = json.load(f)

            return [{key: json_normalize(value)} for key, value in dicts.items()]
    else:
        raise ValueError('File {} does not exist'.format(json_template))
