from click.testing import CliRunner

from archetypal import get_eplus_dire
from archetypal.cli import cli


class TestCli():

    def test_hello_world(self, config):
        runner = CliRunner()
        examples = get_eplus_dire() / "ExampleFiles"
        test_file = examples / "2ZoneDataCenterHVAC_wEconomizer.idf"
        test_file = "tests/input_data/umi_samples/B_Off_0.idf"
        result = runner.invoke(cli,
                               ['--use-cache', '--cache-folder',
                                'tests/.temp/cache', '--data-folder',
                                'tests/.temp/data', '--imgs-folder',
                                'tests/.temp/images', '--logs-folder',
                                'tests/.temp/logs',
                                '--log-console',
                                'reduce',
                                '-np',
                                test_file],
                               catch_exceptions=False,
                               )
        print(result.stdout)
        assert result.exit_code == 0
