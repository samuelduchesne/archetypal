import pyumi as pu
from pyumi import load_umi_template
import matplotlib as mpl
import os, shutil

mpl.use('Agg')  # use agg backend so you don't need a display on travis-ci

# remove the .temp folder if it already exists so we start fresh with tests
if os.path.exists('.temp'):
    shutil.rmtree('.temp')

pu.config(log_console=True, log_file=True, use_cache=True,
          data_folder='.temp/data', logs_folder='.temp/logs',
          imgs_folder='.temp/imgs', cache_folder='.temp/cache',
          umitemplate='../../data/BostonTemplateLibrary.json')


def test_load_umi_template():
    data_json = pu.settings.umitemplate
    assert len(load_umi_template(data_json)) == 17