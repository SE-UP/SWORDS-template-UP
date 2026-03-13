# pylint: skip-file
"""
Tests for test configuration retrieval methods in variable collection
"""
import pytest
from unittest.mock import MagicMock
import os

from collect_variables.scripts.parse_test_config.parse_python_test_configs\
    import get_testconfig_from_toml_file, get_testconfig_from_cfg_file, collect_testing_configuration

@pytest.fixture
def path():
    return os.path.dirname(__file__)

@pytest.fixture
def pyproject_file(path):
    return os.path.join(path, "test_data/config_data/pyproject.toml")

@pytest.fixture
def pytest_ini_file(path):
    return os.path.join(path, "test_data/config_data/pytest.ini")

@pytest.fixture
def config_data_path(path):
    return os.path.join(path, "test_data/config_data")

"""
Tests for parse_python_test_configs.py
"""

def test_get_pyproject_test_config(pyproject_file):

    assert os.path.exists(pyproject_file) == True

    result = get_testconfig_from_toml_file(pyproject_file, ["tool.pytest.ini_options", "tool.pytest", "pytest"])
    print(result)

    assert result["testpaths"][0] == "tests"
    assert result["python_files"] == []


def test_get_pytest_ini_test_config(pytest_ini_file):

    assert os.path.exists(pytest_ini_file) == True

    result = get_testconfig_from_cfg_file(pytest_ini_file, "pytest")
    print(result)

    assert len(result["testpaths"]) == 3
    assert result["testpaths"][1] == "testing"
    assert result["python_files"] == []


def test_collect_testing_configuration(config_data_path):

    assert os.path.exists(config_data_path) == True

    result = collect_testing_configuration(config_data_path)
    print(result)

    assert result["pyproject.toml"]["testpaths"][0] == "tests"
    assert result["pyproject.toml"]["python_files"] == []

    assert len(result["pytest.ini"]["testpaths"]) == 3
    assert result["pytest.ini"]["testpaths"][1] == "testing"
    assert result["pytest.ini"]["python_files"] == []

