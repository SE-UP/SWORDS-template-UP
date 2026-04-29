# pylint: skip-file
"""
Tests for test configuration retrieval methods in variable collection
"""
import pytest
from unittest.mock import MagicMock
import os

from collect_variables.scripts.parse_test_config.parse_r_test_configs \
    import parse_dcf_file, collect_testing_configuration

@pytest.fixture
def path():
    return os.path.dirname(__file__)

@pytest.fixture
def testthat_directory(path):
    return os.path.join(path, "test_data/config_data/R/testthat")

@pytest.fixture
def tinytest_directory(path):
    return os.path.join(path, "test_data/config_data/R/tinytest")

@pytest.fixture
def runit_directory(path):
    return os.path.join(path, "test_data/config_data/R/runit")

@pytest.fixture
def multi_directory(path):
    return os.path.join(path, "test_data/config_data/R/multi")


"""
Tests for parse_r_test_configs.py
"""

def test_config_parsing(testthat_directory):
    """
    Tests whether `parse_dcf_file` actually finds the package definition
     and the dependency to `testthat`
    :param testthat_directory: The root directory.
    """

    config_file = os.path.join(testthat_directory, "DESCRIPTION")

    result = parse_dcf_file(config_file)

    assert result["has_package_definition"] == True
    assert result["uses_testthat"] == True
    assert result["uses_runit"] == False
    assert result["uses_tinytest"] == False


def test_multi_config_parsing(multi_directory):
    """
    Tests whether `parse_dcf_file` actually finds the package definition
     and the dependency to `testthat` and `tinytest`
    :param testthat_directory: The root directory.
    """

    config_file = os.path.join(multi_directory, "DESCRIPTION")

    result = parse_dcf_file(config_file)

    assert result["has_package_definition"] == True
    assert result["uses_testthat"] == True
    assert result["uses_runit"] == False
    assert result["uses_tinytest"] == True


def test_testthat_config(testthat_directory):
    """
    Tests whether `collect_testing_configuration` actually correctly
    identifies "tests/testthat" as test path.
    :param testthat_directory: The root directory.
    """

    assert os.path.exists(testthat_directory) == True

    result = collect_testing_configuration(testthat_directory)

    assert result["testpaths"][0] == "tests/testthat"


def test_tinytest_config(tinytest_directory):
    """
    Tests whether `collect_testing_configuration` actually correctly
    identifies "inst/tinytest" as test path.
    :param tinytest_directory: The root directory.
    """

    assert os.path.exists(tinytest_directory) == True

    result = collect_testing_configuration(tinytest_directory)

    assert result["testpaths"][0] == "inst/tinytest"


def test_runit_config(runit_directory):
    """
    Tests whether `collect_testing_configuration` actually correctly
    identifies "tests" as test path.
    :param runit_directory: The root directory.
    """

    assert os.path.exists(runit_directory) == True

    result = collect_testing_configuration(runit_directory)

    assert result["testpaths"][0] == "tests"


def test_multi_config(multi_directory):
    """
    Tests whether `collect_testing_configuration` actually correctly
    identifies "tests/testthat" and "inst/tinytest" as test paths.
    :param multi_directory: The root directory.
    """

    assert os.path.exists(multi_directory) == True

    result = collect_testing_configuration(multi_directory)

    assert len(result["testpaths"]) == 2
    assert result["testpaths"][0] == "tests/testthat"
    assert result["testpaths"][1] == "inst/tinytest"



