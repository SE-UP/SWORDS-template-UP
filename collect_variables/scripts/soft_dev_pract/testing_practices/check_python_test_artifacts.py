"""
This module contains functionality to extract test artifacts for Python
and leverages the 'parse_python_test_configs.py' for fetching the configuration.
"""

import os
from typing import List

from collect_variables.scripts.parse_test_config.parse_python_test_configs \
    import collect_testing_configuration


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


def find_test_artifacts(root_path: str) -> List[str]:
    """
    Validates the test paths by checking for non-empty Python files within each test path.

    This function retrieves the test paths from various configuration files and checks each
    path to verify if it contains non-empty Python files.

    Args:
        root_path (str): The directory path to search for test configuration files.

    Returns:
        List[str]: A list of valid test paths containing non-empty Python files.
    """
    testconfigs = collect_testing_configuration(root_path)

    test_paths = []

    found_files = [path for path in test_paths if find_non_empty_python_files(path)]


    # for each config, find the test files


