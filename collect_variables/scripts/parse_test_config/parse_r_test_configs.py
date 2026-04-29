"""
This module contains functionality to extract test configurations from R DESCRIPTION FILES.
The main function is 'collect_testing_configuration'.
"""

import os
import re
from typing import Dict, List

# Define global test paths
test_paths: Dict[str, List[str]] = {
    'testthat': ['tests/testthat'],
    'RUnit': ['tests'],
    'tinytest': ['inst/tinytest']
}

def parse_dcf_file(file_path: str) -> Dict[str, bool]:
    """
    Parses a DESCRIPTION file formatted in DCF (Debian Control File) format.

    Parameters:
    - file_path: str, path to the DESCRIPTION file.

    Returns:
    - dict containing information on package setup.
    """
    project_config: Dict[str, bool] = {
        'has_package_definition': False,
        'uses_testthat': False,
        'uses_runit': False,
        'uses_tinytest': False
    }

    if not os.path.exists(file_path):
        print(f"File {file_path} does not exist.")
        return project_config

    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()

    # Parse Package Name
    package_name_match = re.search(r'^Package:\s*(\w+)', content, re.MULTILINE)
    if package_name_match:
        project_config['has_package_definition'] = True

    # Regular expression to parse dependencies with optional version constraint
    dependencies_pattern = re.compile(r'\b(?:Depends|Imports|Suggests):\s*((?:\w+(?:\s*\([^)]+\))?\s*(?:,|$)\s*)+)', re.MULTILINE)

    # Find all dependencies
    dependencies_blocks = dependencies_pattern.findall(content)
    for block in dependencies_blocks:
        package_matches = re.findall(r'(\w+)(?:\s*\(([^)]+)\))?', block)
        for package, _ in package_matches:
            if package == 'testthat':
                project_config['uses_testthat'] = True
            if package == 'RUnit':
                project_config['uses_runit'] = True
            if package == 'tinytest':
                project_config['uses_tinytest'] = True

    return project_config

def collect_testing_configuration(directory: str) -> Dict[str, Dict[str, List[str]]]:
    """
    Collects the testing configuration by checking the package definition and adds test paths.

    Parameters:
    - directory: str, path to the directory containing the DESCRIPTION file.

    Returns:
    - dict containing the testing path information.
    """
    file_path = os.path.join(directory, "DESCRIPTION")

    config = parse_dcf_file(file_path)
    complete_config = {'testpaths': []}

    if config['has_package_definition']:
        if config['uses_testthat']:
            complete_config['testpaths'].extend(test_paths['testthat'])
        if config['uses_runit']:
            complete_config['testpaths'].extend(test_paths['RUnit'])
        if config['uses_tinytest']:
            complete_config['testpaths'].extend(test_paths['tinytest'])

    return complete_config
