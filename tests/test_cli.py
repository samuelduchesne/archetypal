from click.testing import CliRunner

from archetypal import get_eplus_dire
from archetypal.cli import cli


class TestCli():
    """Defines tests for usage of the archetypal Command Line Interface"""

    def test_reduce(self, config):
        """Tests the 'reduce' method"""
        runner = CliRunner()
        examples = get_eplus_dire() / "ExampleFiles"
        test_file = examples / "2ZoneDataCenterHVAC_wEconomizer.idf"
        test_file = "/Users/samuelduchesne/Dropbox/Polytechnique/Doc/software/archetypal/tests/input_data/necb/NECB 2011-FullServiceRestaurant-NECB HDD Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf"
        result = runner.invoke(cli,
                               ['--use-cache', '--cache-folder',
                                'tests/.temp/cache', '--data-folder',
                                'tests/.temp/data', '--imgs-folder',
                                'tests/.temp/images', '--logs-folder',
                                'tests/.temp/logs',
                                '--log-console',
                                'reduce',
                                '-w',
                                "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw",
                                '-np',
                                test_file],
                               catch_exceptions=False,
                               )
        print(result.stdout)
        assert result.exit_code == 0
