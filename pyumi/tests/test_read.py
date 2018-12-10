import os
import unittest

from pyumi import load_umi_template as lm
from pyumi.simple_glazing import simple_glazing


class pyumitests(unittest.TestCase):

    def test_load_umi_template(self):
        proj_name = 'template-libraries'
        base_directory = os.path.join('data', proj_name)
        data_json = os.path.join(base_directory, 'boston-default.json')
        self.assertTrue(len(lm(data_json)) == 17, msg='got {} instead of 17'
                        .format(len(lm(data_json))))

    def test_simple_glazing_system(self):
        dict = simple_glazing(0.6, 2.2, 0.21)
        self.assertEqual(dict['Conductivity'], 0.11992503503877955)
