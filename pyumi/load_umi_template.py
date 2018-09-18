import json

from pandas.io.json import json_normalize  # package for flattening json in pandas df


def load_umi_template(json_template):
    """

    :param json_template: absolute or relative filepath to an umi json_template file.
    :return: 17 DataFrames, one for each component groups

    Example
    -------



    """
    with open(json_template) as f:
        dicts = json.load(f)

        return [{key: json_normalize(value)} for key, value in dicts.items()]
