import pytest

from archetypal import IDF


class TestIDF:
    @pytest.fixture(scope="session")
    def idf_model(self, config):
        """An IDF model. Yields both the idf and the sql"""
        file = "tests/input_data/umi_samples/B_Off_0.idf"
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        yield IDF(file, epw=w)

    def test_processed_results(self, idf_model):
        assert idf_model.processed_results
