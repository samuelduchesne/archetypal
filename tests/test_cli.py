import os

import pytest
from click.testing import CliRunner
from path import Path

from archetypal import settings
from archetypal.cli import cli
from archetypal.utils import log


class TestCli:
    """Defines tests for usage of the archetypal Command Line Interface"""

    def test_reduce(self):
        """Tests the 'reduced_model' method"""
        runner = CliRunner()
        base = Path("tests/input_data/umi_samples")
        outname = "tests/.temp/warehouse.json"
        result = runner.invoke(
            cli,
            [
                "-csd",
                "--cache-folder",
                "tests/.temp/cache",
                "--data-folder",
                "tests/.temp/data",
                "--imgs-folder",
                "tests/.temp/images",
                "--logs-folder",
                "tests/.temp/logs",
                "--ep_version",
                settings.ep_version,
                "reduce",
                "-w",
                "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_*.epw",
                base / "*Res*.idf",
                "-o",
                outname,
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert Path(outname).exists()

    @pytest.mark.skipif(
        os.environ.get("CI", "False").lower() == "true",
        reason="Skipping this test on CI environment.",
    )
    def test_transition_dir_file_mixed(self):
        """Tests the transition method for the CLI using a mixture of a directory
        (Path.isdir()) and a file Path.isfile()"""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--cache-folder",
                "tests/.temp/cache",
                "--data-folder",
                "tests/.temp/data",
                "--imgs-folder",
                "tests/.temp/images",
                "--logs-folder",
                "tests/.temp/logs",
                "transition",
                "-v",
                "9.2",
                "tests/input_data/problematic/ASHRAE90.1_ApartmentHighRise_STD2016_Buffalo.idf",
                "tests/input_data/problematic/*.idf",  # Path with wildcard
                "tests/input_data/problematic",  # Just a path
            ],
            catch_exceptions=False,
        )
        log(result.stdout)
        assert result.exit_code == 0
