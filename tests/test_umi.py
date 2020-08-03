import collections
import json
import os

import pytest

from archetypal import settings, get_eplus_dirs
from archetypal.umi_template import UmiTemplateLibrary
from tests.conftest import no_duplicates


class TestUmiTemplate:
    """Test suite for the UmiTemplateLibrary class"""

    def test_template_to_template(self, config):
        """load the json into UmiTemplateLibrary object, then convert back to json and
        compare"""

        file = "tests/input_data/umi_samples/BostonTemplateLibrary_nodup.json"

        a = UmiTemplateLibrary.read_file(file).to_dict()
        b = TestUmiTemplate.read_json(file)
        assert json.loads(json.dumps(a)) == json.loads(json.dumps(b))

    def test_template_to_tempalte_json(self, config):
        file = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"

        UmiTemplateLibrary.read_file(file).to_json("BostonTemplateLibrary_ar.json")

    def test_umitemplate(self, config):
        """Test creating UmiTemplateLibrary from 2 IDF files"""
        idf_source = [
            "tests/input_data/necb/NECB 2011-FullServiceRestaurant-NECB HDD Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf",
            get_eplus_dirs(settings.ep_version)
            / "ExampleFiles"
            / "VentilationSimpleTest.idf",
        ]
        wf = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        a = UmiTemplateLibrary.read_idf(idf_source, wf, name="Mixed_Files",
                                        processors=-1)

        data_dict = a.to_dict()
        a.to_json()
        assert no_duplicates(data_dict)

    @pytest.mark.skipif(
        os.environ.get("CI", "False").lower() == "true",
        reason="not necessary to test this on CI",
    )
    def test_umi_samples(self, config):
        idf_source = [
            "tests/input_data/umi_samples/B_Off_0.idf",
            "tests/input_data/umi_samples/B_Ret_0.idf",
            "tests/input_data/umi_samples/B_Res_0_Masonry.idf",
            "tests/input_data/umi_samples/B_Res_0_WoodFrame.idf",
        ]
        wf = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        a = UmiTemplateLibrary.read_idf(idf_source, wf, name="Mixed_Files")

        data_dict = a.to_dict()
        assert no_duplicates(data_dict)

    @staticmethod
    def read_json(file):
        with open(file, "r") as f:
            a = json.load(f, object_pairs_hook=collections.OrderedDict)
            data_dict = collections.OrderedDict(
                {
                    "GasMaterials": [],
                    "GlazingMaterials": [],
                    "OpaqueMaterials": [],
                    "OpaqueConstructions": [],
                    "WindowConstructions": [],
                    "StructureDefinitions": [],
                    "DaySchedules": [],
                    "WeekSchedules": [],
                    "YearSchedules": [],
                    "DomesticHotWaterSettings": [],
                    "VentilationSettings": [],
                    "ZoneConditionings": [],
                    "ZoneConstructionSets": [],
                    "ZoneLoads": [],
                    "Zones": [],
                    "WindowSettings": [],
                    "BuildingTemplates": [],
                }
            )
            data_dict.update(a)
            return data_dict
