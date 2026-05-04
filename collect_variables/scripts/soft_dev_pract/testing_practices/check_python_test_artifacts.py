"""
This module contains functionality to extract test artifacts for Python
and leverages the 'parse_python_test_configs.py' for fetching the configuration.
"""

import os
import fnmatch
from typing import Dict, List

from collect_variables.scripts.parse_test_config.parse_python_test_configs \
    import extract_testing_configuration


def is_non_empty_python_file(file_path: str) -> bool:
    """
    Checks if a path refers to a non-empty Python file.

    Args:
        file_path (str): The file path to check.

    Returns:
        bool: True if file_path is a non-empty Python file, False otherwise.
    """
    if file_path.endswith('.py'):
        if os.path.getsize(file_path) > 0:
            return True
    return False


def find_non_empty_python_files(directory: str) -> List[str]:
    """
    Recursively finds all non-empty python files in a directory.

    Args:
        directory (str): The directory path to check.

    Returns:
        List[str]: the non-empty python files.
    """

    nonempty_files = []

    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            if is_non_empty_python_file(file_path):
                nonempty_files.append(file_path)

    return nonempty_files


def count_non_empty_python_files(directory: str) -> int:
    """
    Recursively counts non-empty Python files.

    Args:
        directory (str): The directory path to check.

    Returns:
        int: the count of non-empty python files.
    """

    nonempty_file_count = 0

    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            if is_non_empty_python_file(file_path):
                nonempty_file_count = nonempty_file_count + 1

    return nonempty_file_count


def search_artifacts_in_paths(root_path: str, test_config: Dict[str, List[str]]) -> List[str]:
    """
    Iterates over all directories in 'testpaths' and searches for files
    matching the globs defined in 'python_files'.

    Parameters:
    - test_config: Dict[str, List[str]]
        A dictionary with two keys:
        - "testpaths": A list of directory paths to be searched.
        - "python_files": A list of globs specifying the file patterns to search for.

    Returns:
    - List[str]:
        A list of full file paths that match the specified globs.
    """
    found_files = []

    for testpath in test_config["testpaths"]:
        tests_root = os.path.join(root_path, testpath)
        for root, _, files in os.walk(tests_root):
            for filepattern in test_config["python_files"]:
                for file in files:
                    if fnmatch.fnmatch(file, filepattern):
                        found_file = os.path.join(root, file)
                        if is_non_empty_python_file(found_file):
                            found_files.append(found_file)
    return found_files


def find_test_artifacts(root_path: str) -> Dict[str, bool]:
    """
    Validates the test paths by checking for non-empty Python files within each test path.

    This function retrieves the test paths from various configuration files and checks each
    path to verify if it contains non-empty Python files.

    Args:
        root_path (str): The directory path to search for test configuration files.

    Returns:
        List[str]: A list of valid test paths containing non-empty Python files.
    """
    test_config = extract_testing_configuration(root_path)

    # We get a dict of the form
    #testconfig : Dict[str, List[str]] = {
    #    "testpaths" : ["tests"],
    #    "python_files" : []
    #}

    # The default test file patterns are `test_*.py` and `*_test.py`
    # This can be overridden with `python_files`

    # Thus, if python_files is empty or does not exist, put the glob expressions to the list.
    if "python_files" not in test_config or len(test_config["python_files"]) == 0:
        test_config["python_files"].extend(["test_*.py", "*_test.py"])

    found_files = search_artifacts_in_paths(root_path, test_config)

    found_configs = test_config["found_configs"]

    test_artifacts: Dict[str, bool] = {
        'has_pyproject_toml' : "pyproject.toml" in found_configs,
        'has_pytest_toml' : "pytest.toml" in found_configs or ".pytest.toml" in found_configs,
        'has_pytest_ini' : "pytest.ini" in found_configs or ".pytest.ini" in found_configs,
        'has_tox_ini' : "tox.ini" in found_configs,
        'has_setup_cfg' : "setup.cfg" in found_configs,
        'has_python_tests': len(found_files) > 0,
    }

    return test_artifacts

