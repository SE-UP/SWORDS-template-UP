"""
This module contains functionality to extract test configuraitons from the following files

- pytest.toml
- .pytest.toml
- pyproject.toml
- pytest.ini
- tox.ini
- setup.cfg

The main function is 'collect_testing_configuration'.
"""

import os
from typing import Optional, List, Dict
import configparser
import re

import sys

# Make sure that TOML parsing works consistently
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def get_testconfig_from_toml_file(file_path: str, table_names: List[str])\
        -> Optional[Dict[str, List[str]]]:
    """
    Extracts the 'testpaths' and 'python_files' arrays from a TOML file.
    and return the test configuration as a dictionary.

    This function reads and parses the content of a TOML file,
    targeting the table_names sections to find the 'testpaths' and 'python_files'.
    It returns the first found 'testpaths' and 'python_files' arrays in a dictionary,
    if existent.

    Args:
        file_path (str): The path to the TOML file.
        table_names (List[str]): the relevant sections

    Returns:
        Optional[Dict[str, List[str]]]: The test configuration (paths and files) and None on error.
    """
    try:
        # Read the file content
        with open(file_path, 'rb') as file:  # Use 'rb' mode for binary reading
            toml_data = tomllib.load(file)

        # Create empty test config
        testconfig : Dict[str, List[str]] = {
            "testpaths" : [],
         "python_files" : []
        }

        # Iterate over sections
        for table_name in table_names:
            keys = table_name.split('.')
            section_content = toml_data
            # Iterate over section name components, if we have e.g. 'tool.pytest.foo'
            for key in keys:
                section_content = section_content.get(key)
                if section_content is None:
                    break

            if isinstance(section_content, dict):
                if 'testpaths' in section_content:
                    testpaths = section_content['testpaths']
                    # Return the first nonempty testpaths list found
                    if isinstance(testpaths, list) and any(testpaths):
                        testconfig["testpaths"] = testpaths

                if 'python_files' in section_content:
                    python_files = section_content['python_files']
                    # Return the first nonempty testpaths list found
                    if isinstance(python_files, list) and any(python_files):
                        testconfig["python_files"] = python_files

                return testconfig

    except FileNotFoundError:
        print(f"The file '{file_path}' was not found.")
    except Exception as e:
        print(f"An error occurred while processing the file: {e}")

    return None


def get_testconfig_from_cfg_file(file_path: str, table_name: str) -> Optional[Dict[str, List[str]]]:
    """
    Extracts the 'testpaths' and 'python_files' arrays from an ini style configuration file.
    and return the test configuration as a dictionary.

    This function reads and parses the content of a configuration file,
    targeting the table_name sections to find the 'testpaths' and 'python_files'.
    It returns the found 'testpaths' and 'python_files' arrays in a dictionary,
    if existent.

    Args:
        file_path (str): The path to the TOML file.
        table_name (str): the table to search the 'testpaths' and 'python_files' entries in.

    Returns:
        Optional[Dict[str, List[str]]]: The test configuration (paths and files) and None on error.
    """
    config = configparser.ConfigParser()

    # Create empty test config
    testconfig : Dict[str, List[str]] = {
        "testpaths" : [],
        "python_files" : []
        }

    try:
        config.read(file_path)

        if table_name in config:
            testpaths = config.get(table_name, 'testpaths', fallback=None)
            if testpaths:
                testconfig["testpaths"] = re.split(r'\s+', testpaths.strip())

            python_files = config.get(table_name, 'python_files', fallback=None)
            if python_files:
                testconfig["python_files"] = re.split(r'\s+', python_files.strip())

        return testconfig

    except Exception as e:
        print(f"An error occurred while parsing the CFG content: {e}")
        return None


def collect_testing_configuration(directory: str) -> Dict[str, Dict[str, List[str]]]:
    """
    Searches for test configuration files in the given directory and extracts 'testpaths'
    and 'python_files' information from all files.

    This function checks for the existence of 'pyproject.toml', 'pytest.toml', '.pytest.toml,
    ''pytest.ini',  'setup.cfg', and 'pytest.toml' in the specified directory.
    It extracts 'testpaths' and 'python_files' information for all those files and returns
    a dictionary with the found information.

    Args:
        directory (str): The directory path to search for test configuration files.

    Returns:
        Dict[str, Dict[str, List[str]]]: A dictionary with the found configuration per file.
    """
    dot_pytest_toml_file =  os.path.join(directory, '.pytest.toml')
    pytest_toml_file = os.path.join(directory, 'pytest.toml')
    pyproject_file = os.path.join(directory, 'pyproject.toml')
    pytest_ini_file = os.path.join(directory, 'pytest.ini')
    tox_ini_file = os.path.join(directory, 'tox.ini')
    setup_cfg_file = os.path.join(directory, 'setup.cfg')

    # Assume we have no config specified
    testconfigs = {}


    # Check for each config file type whether test folders were found.
    if os.path.exists(pytest_toml_file):
        print(f"Found pytest.toml file at: {pytest_toml_file}")
        testconfigs["pytest.toml"] = get_testconfig_from_toml_file(pytest_toml_file, ["pytest"])

    if os.path.exists(dot_pytest_toml_file):
        print(f"Found .pytest.toml file at: {dot_pytest_toml_file}")
        testconfigs[".pytest.toml"] = (
            get_testconfig_from_toml_file(dot_pytest_toml_file, ["pytest"]))

    if os.path.exists(pyproject_file):
        print(f"Found pyproject.toml file at: {pyproject_file}")
        testconfigs["pyproject.toml"] = (
            get_testconfig_from_toml_file(pyproject_file,
                                          ["tool.pytest", "tool.pytest.ini_options", "pytest"]))

    if os.path.exists(pytest_ini_file):
        print(f"Found pytest.ini file at: {pytest_ini_file}")
        testconfigs["pytest.ini"] = get_testconfig_from_cfg_file(pytest_ini_file, "pytest")

    if os.path.exists(tox_ini_file):
        print(f"Found tox.ini file at: {tox_ini_file}")
        testconfigs["tox.ini"] = get_testconfig_from_cfg_file(tox_ini_file, "pytest")

    if os.path.exists(setup_cfg_file):
        print(f"Found setup.cfg file at: {setup_cfg_file}")
        testconfigs["setup.cfg"] = get_testconfig_from_cfg_file(setup_cfg_file, "tool:pytest")

    return testconfigs
