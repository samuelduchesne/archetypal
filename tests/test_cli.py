import os

import pytest
from click.testing import CliRunner
from path import Path

from archetypal import settings
from archetypal.cli import cli
from archetypal.utils import log

from .conftest import data_dir

pytestmark = pytest.mark.slow


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
