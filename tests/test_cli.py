import os

import pytest
from click.testing import CliRunner
from path import Path

from archetypal import settings
from archetypal.cli import cli
from archetypal.utils import log

from .conftest import data_dir


class TestCli:
    """Defines tests for usage of the archetypal Command Line Interface"""

    @pytest.mark.skipif(
        os.environ.get("CI", "False").lower() == "true",
        reason="Some issue with click CLI test suite makes this fail.",
    )
    def test_reduce(self):
        """Tests the 'reduced_model' method"""
        runner = CliRunner()
        base = Path(data_dir / "umi_samples")
        outname = settings.cache_folder / "warehouse.json"
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
                data_dir / "CAN_PQ_Montreal.Intl.AP.716270_*.epw",
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
        (Path.is_dir()) and a file Path.is_file()"""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--cache-folder",
                os.getenv("ARCHETYPAL_CACHE") or "tests/.temp/cache",
                "--data-folder",
                os.getenv("ARCHETYPAL_DATA") or "tests/.temp/data",
                "--imgs-folder",
                os.getenv("ARCHETYPAL_IMAGES") or "tests/.temp/images",
                "--logs-folder",
                os.getenv("ARCHETYPAL_LOGS") or "tests/.temp/logs",
                "transition",
                "-v",
                "9.2",
                str(data_dir / "problematic/ASHRAE90.1_ApartmentHighRise_STD2016_Buffalo.idf"),
                str(data_dir / "problematic/*.idf"),  # Path with wildcard
                str(data_dir / "problematic"),  # Just a path
            ],
            catch_exceptions=False,
        )
        log(result.stdout)
        assert result.exit_code == 0
