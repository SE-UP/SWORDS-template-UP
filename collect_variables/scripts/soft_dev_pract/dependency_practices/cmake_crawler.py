"""
Clone and scan C++ repos based on the following CMake files:
- CMakeLists.txt
- CMakeLists.txt.in
- *.cmake
- *.cmake.in

Requires input CSV with columns:
- doi (JOSS DOI)
- entry_number (JOSS DOI suffix)
- html_url (GitHub repo URL)
- repo_name (Git repository name)

Adds columns:
- nothing

Sets columns:
- Project ID (DOI) : str
- Has CMakeLists : bool
- Languages : str
- Dependencies Found : bool
- Pinned Req. Dependencies : bool
- Pinned Opt. Dependencies : bool
- Tests Found : bool
- Uses GTest  : bool
TODO: Update this

Usage:
  python3 cmake_crawler.py --input path/to/input.csv --output path/to/output.csv
"""

import csv
import json
import re
import argparse
import subprocess
import os
import time
from typing import List, Optional

import pandas as pd


# Regular expressions which should eventually be improved or even replaced with
# proper CMake file parsing.
PROJECT_REGEX = (r'\s*(project|PROJECT)\s*\(\s*([^\s\)]+)\s*'
                 r'(?:VERSION\s*((([0-9]+)|\$\{[a-zA-Z]+\w*\})'
                 r'(?:\.(([0-9]+)(\$\{[a-zA-Z]+\w*\})))*)\s*)?'
                 r'(?:COMPAT_VERSION\s*([0-9]+(?:\.[0-9]+)*)\s*)?'
                 r'(?:DESCRIPTION\s*"([^"]*)"\s*)?'
                 r'(?:HOMEPAGE_URL\s*"([^"]*)"\s*)?'
                 r'(?:LANGUAGES\s+([^)]+))?\s*'
                 r'(?:VERSION\s*((([0-9]+)|\$\{[a-zA-Z]+\w*\})'
                 r'(?:\.(([0-9]+)(\$\{[a-zA-Z]+\w*\})))*)\s*)?\)')

FIND_PACKAGE_REGEX = (r'\s*(find_package|FIND_PACKAGE)\s*\(\s*([^\s\)]+)\s*'
                      r'(?:([0-9\.]+))?\s*'
                      r'(REQUIRED)?\s*(COMPONENTS\s*([^\)]*))?')

ADD_TEST_REGEX       = r'\s*(add_test|ADD_TEST)\s*\([^\)]+\)'
GTEST_DISCOVER_REGEX = r'\s*(gtest_discover_tests|GTEST_DISCOVER_TESTS)\s*\([^\)]+\)'



def clone_repo(project_id : str, repo_url : str, clone_path : str) -> Optional[str]:
    """
    Clones the given GitHub repository into the specified path.

    :param project_id: The project ID (usually JOSS suffix) of the project.
    :param repo_url: URL of the repository to clone.
    :param clone_path: Path where the repository should be cloned.
    """
    try:
        # Ensuring the clone path exists
        os.makedirs(clone_path, exist_ok=True)

        # Constructing the full clone path
        repo_name = project_id + '_' + repo_url.split('/')[-1].replace('.git', '')
        full_clone_path = os.path.join(clone_path, repo_name)

        # Running the git clone command if the directory exists but is empty
        if os.path.exists(full_clone_path) and os.listdir(full_clone_path):
            print(f"Directory for repo {repo_url} already exists in {full_clone_path}")
        else:
            time.sleep(30)
            subprocess.run(["git", "clone", repo_url, full_clone_path], check=True)
            print(f"Successfully cloned: {repo_url} into {full_clone_path}")

        return full_clone_path
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while cloning the repository: {e}")
        return None


def find_cmake_files(base_path : str) -> List[str]:
    """
    Finds all CMakeLists.txt and *.cmake files within the given
    directory and subdirectories. Also includes template variants of those
    files.

    :param base_path: The directory path to search within.
    :return: A list of paths to CMakeLists.txt files.
    """
    cmake_lists_paths = []

    # Traverse the directory tree
    for (root, _dirs, files) in os.walk(base_path):
        for file in files:
            if ((file in ("CMakeLists.txt", "CMakeLists.txt.in"))
                    or file.endswith('.cmake') or file.endswith('.cmake.in')):
                # Append the full path to the list
                cmake_lists_paths.append(os.path.join(root, file))

    return cmake_lists_paths


def collect_repo_structure(base_path : str):
    """
    Checks the base_path for the existence of the following files

    - Makefile
    - CMakeLists.txt
    - pyproject.toml
    - requirements.txt
    - DESCRIPTION

    Also, returns whether test folders could be found.

    :param base_path: The path to search the files in
    :return: A JSON object containing the info about the existence as record of boolean values.
    """

    has_main_makefile    = False
    has_main_cmakelists  = False
    has_pyproject_toml   = False
    has_requirements_txt = False
    has_description      = False
    has_test_folders     = False

    files = [f.path for f in os.scandir(base_path) if not f.is_dir()]
    for file in list(files):
        file_basename = file.split('/')[-1]
        if file_basename == "Makefile":
            has_main_makefile = True
            continue

        if file_basename == "CMakeLists.txt":
            has_main_cmakelists = True
            continue

        if file_basename == "pyproject.toml":
            has_pyproject_toml = True
            continue

        if file_basename == "requirements.txt":
            has_requirements_txt = True
            continue

        if file_basename == "DESCRIPTION":
            has_description = True

    folders = [f.path for f in os.scandir(base_path) if f.is_dir()]
    for folder in list(folders):
        if "test" in folder.split('/')[-1].lower():
            has_test_folders = True

    result = {
        "has_main_makefile"    : has_main_makefile,
        "has_main_cmakelists"  : has_main_cmakelists,
        "has_pyproject_toml"   : has_pyproject_toml,
        "has_requirements_txt" : has_requirements_txt,
        "has_description"      : has_description,
        "has_test_folders"     : has_test_folders
    }

    return json.dumps(result, indent=4, sort_keys=True)


def extract_languages(languages_str : str) -> List[str]:
    """
    Extracts the programming language list from a potentially unclean project
    stanza content.

    :param languages_str: The stanza content
    :return: The clean string containing the languages only.
    """
    if languages_str:
        #print(f"Found Language String: {languages_str}")
        langs = languages_str.strip().split()
        filtered_langs = []
        # Keep everything until end of list or meeting one of Remove everything
        # VERSION COMPAT_VERSION DESCRIPTION HOMEPAGE_URL
        for lang in langs:
            if lang.upper() in ("VERSION", "COMPAT_VERSION", "DESCRIPTION", "HOMEPAGE_URL"):
                break

            filtered_langs.append(lang)

        return filtered_langs

    return []


def parse_cmake_files(file_paths : List[str]) -> Optional[str]:
    """
    Parses CMake files to extract project information, dependencies, and test details.

    :param file_paths: List of paths to CMakeLists.txt files.
    :return: JSON object containing languages, dependencies, uses_gtest, and tests_found.
    """

    # Prepare JSON object
    result = {
        "has_cmakelists"   : bool(file_paths),
        "languages"        : [],
        "dependencies"     : [],
        "opt_dependencies" : [],
        "uses_gtest"       : False,
        "uses_catch2"      : False,
        "tests_found"      : False
    }

    languages        = set()
    dependencies     = []
    opt_dependencies = []

    try:
        for file_path in file_paths:
            print(f"Processing CMake file {file_path}")

            with open(file_path, 'r', encoding='utf-8') as cmake_file:
                file_content = cmake_file.read().replace('\n', '')
                project_match = re.search(PROJECT_REGEX, file_content)
                if project_match:
                    #print(f"Found Project Stanza")
                    # Extract the clean language list and update the languages set.
                    languages.update(extract_languages(project_match.group(12)))

            with open(file_path, 'r', encoding='utf-8') as cmake_file:
                file_content = cmake_file.read().replace('\n', '')
                # Check for add_test command
                if re.search(ADD_TEST_REGEX, file_content):
                    #print(f"Found at least one test")
                    result["tests_found"] = True

            with open(file_path, 'r', encoding='utf-8') as cmake_file:
                file_content = cmake_file.read().replace('\n', '')
                # Check for gtest_discover_tests command
                if re.search(GTEST_DISCOVER_REGEX, file_content):
                    #print(f"Found at least one test")
                    result["tests_found"] = True

            with open(file_path, 'r', encoding='utf-8') as file:
                for line in file:
                    # Check for find_package command to extract dependencies
                    find_package_match = re.search(FIND_PACKAGE_REGEX, line)
                    if find_package_match:

                        package_name = find_package_match.group(2)

                        dep_info = {
                            "name"     : package_name,
                            "version"  : find_package_match.group(3) if find_package_match.group(3)
                                         else "Any",
                        }

                        # If the dependency is required
                        if find_package_match.group(4):
                            dependencies.append(dep_info)
                        else:
                            opt_dependencies.append(dep_info)

                        # Check if the package name is GTest
                        if package_name.lower() == "gtest":
                            result["uses_gtest"] = True

                        # Check if the package name is Catch2
                        if package_name.lower() == "catch2":
                            result["uses_catch2"] = True

        result["languages"] = list(languages)
        result["languages"].sort()
        # Remove duplicate entries in the dependencies
        result["dependencies"] = (pd.DataFrame(dependencies).drop_duplicates()
                                  .to_dict('records'))
        result["opt_dependencies"] = (pd.DataFrame(opt_dependencies).drop_duplicates()
                                      .to_dict('records'))

        return json.dumps(result, indent=4, sort_keys=True)

    except FileNotFoundError as e:
        print(f"A file was not found: {e}")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def has_pinned_dependency(dep_list) -> bool:
    """
    Returns true if at least one of the dependencies in the list has a defined
    version.
    :param dep_list: The list of dependencies.
    :return: True, if a specific version dependency is found and False, else.
    """
    for dep in dep_list:
        if not dep["version"] == "Any":
            return True

    return False


def analyze_repo(joss_id, repo_url):
    """
    Analyses the repo and returns a tuple following information:

    - Information extracted from CMake files
    - Information about configuration files and directories

    :param joss_id: The JOSS ID
    :param repo_url: The repository URL
    :return: A tuple with the CMake file information and the repo structure.
    """
    # Clone the repository
    repo_path = clone_repo(joss_id, repo_url, "./")
    # Find CMake files paths
    cmake_lists_paths = find_cmake_files(repo_path)
    # Analyse the CMake files and get the JSON format data
    result_json    = parse_cmake_files(cmake_lists_paths)
    repo_structure = collect_repo_structure(repo_path)

    return result_json, repo_structure


def process_csv_and_handle_repos(csv_file_path : str, csv_outfile_path : str) -> None:
    """
    Processes a CSV file, iterates over rows to handle repository cloning and path finding.

    :param csv_file_path: Path to the CSV file.
    :param csv_outfile_path: Path to the output CSV file.
    """
    try:
        with open(csv_file_path, mode='r', newline='', encoding='utf-8') as file:

            results = []

            #reader = csv.DictReader(file, delimiter=";")

            for row in csv.DictReader(file, delimiter=";"):
                entry_number = row.get("joss_id", "")
                repo_url     = row.get("html_url", "")

                print(f"Crawling {row.get("doi", "")} with URL {repo_url}.")


                result_json, repo_structure = analyze_repo(entry_number, repo_url)

                data      = json.loads(result_json)
                structure = json.loads(repo_structure)

                row["doi"] = row.get("doi", "")
                row["has_root_cmakelists"]  = structure["has_main_cmakelists"]
                row["has_root_makefile"]    = structure["has_main_makefile"]
                row["has_pyproject_toml"]   = structure["has_pyproject_toml"]
                row["has_requirements_txt"] = structure["has_requirements_txt"]
                row["has_description"]      = structure["has_description"]
                row["has_test_folders"]     = structure["has_test_folders"]

                row["has_cmakefiles"] = data["has_cmakelists"]
                row["cmake_languages"] = ", ".join(data["languages"])
                row["has_cmake_dependencies"] = (bool(data["dependencies"])
                                                or bool(data["opt_dependencies"]))
                row["has_cmake_pinned_req_deps"] = has_pinned_dependency(data["opt_dependencies"])
                row["has_cmake_pinned_opt_deps"] = has_pinned_dependency(data["dependencies"])
                row["has_cmake_tests"] = data["tests_found"]
                row["has_gtest_dep"]   = data["uses_gtest"]
                row["has_catch2_dep"]  = data["uses_catch2"]

                results.append(row)

                print(f"Finished analysis of {row.get("doi", "")} with URL {repo_url}.")


        with open(csv_outfile_path, mode='w', newline='', encoding='utf-8') as csvfile:
            # Define the output fieldnames.
#            out_fieldnames = (reader.fieldnames or []) + ["has_cmakefiles", "has_root_cmakelists",
            out_fieldnames = ["doi", "has_cmakefiles", "has_root_cmakelists",
                               "has_root_makefile", "has_pyproject_toml",
                              "has_requirements_txt", "has_description", "cmake_languages",
                              "has_cmake_dependencies", "has_cmake_pinned_req_deps",
                              "has_cmake_pinned_opt_deps", "has_test_folders",
                              "has_cmake_tests", "has_gtest_dep", "has_catch2_dep"]

            csv_writer = csv.DictWriter(csvfile, delimiter=",", fieldnames=out_fieldnames,
                                        extrasaction='ignore')
            csv_writer.writeheader()
            csv_writer.writerows(results)


    except FileNotFoundError:
        print(f"The file {csv_file_path} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")


def main() -> None:
    """
    Parse CLI args and run.
    """
    parser = argparse.ArgumentParser(description="Parse input CSV file, crawl (clone) and analyse"
                                                 "CMake project and generate a CSV result.")
    parser.add_argument("--input", help="Path to the input CSV file.")
    parser.add_argument("--output", help="Path to the output CSV file.")

    args = parser.parse_args()

    process_csv_and_handle_repos(args.input, args.output)


if __name__ == "__main__":
    main()
