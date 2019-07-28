from click.testing import CliRunner

from archetypal import get_eplus_dire
from archetypal.cli import cli


class TestCli():

    def test_reduce(self, config):
        runner = CliRunner()
        examples = get_eplus_dire() / "ExampleFiles"
        test_file = examples / "2ZoneDataCenterHVAC_wEconomizer.idf"
        test_files = ["tests/input_data/necb/NECB 2011-MediumOffice-NECB HDD "
                      "Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf",
                      "tests/input_data/necb/NECB 2011-LargeOffice-NECB HDD "
                      "Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf"]
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
                                *test_files],
                               catch_exceptions=False,
                               )
        print(result.stdout)
        assert result.exit_code == 0
