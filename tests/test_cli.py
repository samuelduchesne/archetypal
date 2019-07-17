from click.testing import CliRunner

from archetypal import reduce


class TestCli():

    def test_hello_world(self):
        runner = CliRunner()
        result = runner.invoke(reduce,
                               ['-np',
                                'tests/input_data/necb/NECB 2011-FullServiceRestaurant-NECB HDD Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf'])
        print(result.stdout)
        assert result.exit_code == 0
