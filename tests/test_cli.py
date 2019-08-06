from click.testing import CliRunner

from archetypal import get_eplus_dire
from archetypal.cli import cli
from path import Path


class TestCli:
    """Defines tests for usage of the archetypal Command Line Interface"""

    def test_reduce(self, config):
        """Tests the 'reduce' method"""
        runner = CliRunner()
        examples = get_eplus_dire() / "ExampleFiles"
        necb = Path("tests/input_data/necb")
        test_file = examples / "2ZoneDataCenterHVAC_wEconomizer.idf"
        test_file_list = [
            "tests/input_data/trnsys/ASHRAE90.1_Warehouse_STD2004_Rochester.idf",
            "tests/input_data/trnsys/ASHRAE90.1_RestaurantSitDown_STD2004_Rochester.idf",
        ]
        test_files = necb.glob("*Retail*.idf")
        result = runner.invoke(
            cli,
            [
                "--use-cache",
                "--cache-folder",
                "tests/.temp/cache",
                "--data-folder",
                "tests/.temp/data",
                "--imgs-folder",
                "tests/.temp/images",
                "--logs-folder",
                "tests/.temp/logs",
                "--log-console",
                "reduce",
                "-n",
                "Retail",
                "-w",
                "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw",
                "-p",
                *test_file_list,
            ],
            catch_exceptions=False,
        )
        print(result.stdout)
        assert result.exit_code == 0
