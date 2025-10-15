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
import pandas as pd

from typing import Dict, List

def clone_repo(repo_url : str, clone_path : str) -> str | None:
    """
    Clones the given GitHub repository into the specified path.

    :param repo_url: URL of the repository to clone.
    :param clone_path: Path where the repository should be cloned.
    """
    try:
        # Ensuring the clone path exists
        os.makedirs(clone_path, exist_ok=True)
        
        # Constructing the full clone path
        repo_name = repo_url.split('/')[-1].replace('.git', '')
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
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if (file in ("CMakeLists.txt", "CMakeLists.txt.in")) or file.endswith('.cmake') or file.endswith('.cmake.in'):
                # Append the full path to the list
                cmake_lists_paths.append(os.path.join(root, file))

    return cmake_lists_paths



def parse_cmake_files(file_paths : List[str]):
    """
    Parses CMake files to extract project information, dependencies, and test details.

    :param file_paths: List of paths to CMakeLists.txt files.
    :return: JSON object containing languages, dependencies, uses_gtest, and tests_found.
    """
    languages = set()
    dependencies = []
    if file_paths:
        has_cmakelists = True
    else:
        has_cmakelists = False
    uses_gtest = False
    tests_found = False

    # Regular expressions which should eventually be improved or even replaced with proper CMake file parsing.
    project_regex = r'\s*(project|PROJECT)\s*\(\s*([^\s\)]+)\s*(?:VERSION\s*((([0-9]+)|\$\{[a-zA-Z]+\w*\})(?:\.(([0-9]+)(\$\{[a-zA-Z]+\w*\})))*)\s*)?(?:COMPAT_VERSION\s*([0-9]+(?:\.[0-9]+)*)\s*)?(?:DESCRIPTION\s*"([^"]*)"\s*)?(?:HOMEPAGE_URL\s*"([^"]*)"\s*)?(?:LANGUAGES\s+([^)]+))?\s*(?:VERSION\s*((([0-9]+)|\$\{[a-zA-Z]+\w*\})(?:\.(([0-9]+)(\$\{[a-zA-Z]+\w*\})))*)\s*)?\)'
    find_package_regex = r'\s*(find_package|FIND_PACKAGE)\s*\(\s*([^\s\)]+)\s*(?:([0-9\.]+))?\s*(REQUIRED)?\s*(COMPONENTS\s*([^\)]*))?'
    add_test_regex = r'\s*(add_test|ADD_TEST)\s*\([^\)]+\)'

    try:
        for file_path in file_paths:
            print(f"Processing CMake file {file_path}")
            
            with open(file_path, 'r', encoding='utf-8') as project_file:
                file_content = project_file.read().replace('\n', '')
                project_match = re.search(project_regex, file_content) 
                if project_match:
                    #print(f"Found Project Stanza")
                    languages_str = project_match.group(12)
                    if languages_str:
                        #print(f"Found Language String: {languages_str}")
                        langs = languages_str.strip().split()
                        filtered_langs = []
                        #Keep everything until end of list or meeting one of Remove everything VERSION COMPAT_VERSION DESCRIPTION HOMEPAGE_URL
                        for lang in langs:
                            if lang.upper() in ("VERSION", "COMPAT_VERSION", "DESCRIPTION", "HOMEPAGE_URL"):
                                break
                            else:
                                filtered_langs.append(lang)
                        languages.update(filtered_langs)
                
            with open(file_path, 'r', encoding='utf-8') as tests_file:
                file_content = tests_file.read().replace('\n', '')
                # Check for add_test command
                if re.search(add_test_regex, file_content):
                    #print(f"Found at least one test")
                    tests_found = True
            
            with open(file_path, 'r', encoding='utf-8') as file:
                for line in file:
                    # Check for find_package command to extract dependencies
                    find_package_match = re.search(find_package_regex, line)
                    if find_package_match:
                        package_name = find_package_match.group(2)
                        version = find_package_match.group(3) if find_package_match.group(3) else "Any"
                        required = True if find_package_match.group(4) == "REQUIRED" else False
                        dependencies.append({
                            "name"     : package_name,
                            "version"  : version,
                            "required" : required
                        })
                        
                        # Check if the package name is GTest
                        if package_name.lower() == "gtest":
                            uses_gtest = True
    
        # Prepare JSON object
        result = {
            "has_cmakelists": has_cmakelists,
            "languages"     : list(languages),
            # Remove duplicate entries in the dependencies
            "dependencies"  : pd.DataFrame(dependencies).drop_duplicates().to_dict('records'),
            "uses_gtest"    : uses_gtest,
            "tests_found"   : tests_found
        }
        
        return json.dumps(result, indent=4, sort_keys=True)

    except FileNotFoundError as e:
        print(f"A file was not found: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")


def generate_csv_row(json_data, project_id : str):
    """
    Converts project data from JSON to a CSV row format.

    :param json_data: JSON data returned from parse_cmake_files.
    :param project_id: Identifier for the project.
    :return: A list representing a CSV row.
    """
    
    data = json.loads(json_data)
    
    # Detected project languages.
    languages = ", ".join(data["languages"])
    
    # Information about dependencies and pinning
    dependencies_found = bool(data["dependencies"])
    pinned_required_dependencies=False
    pinned_optional_dependencies=False
    
    for dep in data["dependencies"]:
        version=dep["version"]
        required=dep["required"]
        if not (version == "Any"):
            if required:
                pinned_optional_dependencies=True
            else:
                pinned_required_dependencies=True
    
    return [
        project_id,
        data["has_cmakelists"],
        languages,
        dependencies_found,
        pinned_required_dependencies,
        pinned_optional_dependencies,
        data["tests_found"],
        data["uses_gtest"]
    ]



def generate_cpp_requirements(dependencies_list : List[Dict], output_file_path : str) -> None:
    """
    Generates a C++ requirements.txt file from a list of dependencies.

    :param dependencies_list: List of dependencies to write.
    :param output_file_path: Path to the output file.
    """
    try:
        with open(output_file_path, 'w') as file:
            #print(f"Dependency list:\n {dependencies_list}")
            for dep in dependencies_list:
                name     = dep["name"]
                version  = dep["version"]
                required = dep["required"]
                
                if version == "Any":
                    file.write(f"{name} [Required={required}]\n")
                else:
                    file.write(f"{name}=={version} [Required={required}]\n")
        
        print(f"Requirements file created successfully: {output_file_path}")
    except Exception as e:
        print(f"An error occurred while writing the requirements file: {e}")


def process_csv_and_handle_repos(csv_file_path : str, csv_outfile_path : str) -> None:
    """
    Processes a CSV file, iterates over rows to handle repository cloning and path finding.

    :param csv_file_path: Path to the CSV file.
    :param csv_outfile_path: Path to the output CSV file.
    """
    try:
        with open(csv_file_path, mode='r', newline='', encoding='utf-8') as file:
            reader = csv.reader(file, delimiter=';')
            
            print(f"Opening CSV file: {csv_file_path}")
            
            # Skip the header row
            next(reader)

            with open(csv_outfile_path, mode='w', newline='', encoding='utf-8') as csvfile:
                csv_writer = csv.writer(csvfile)
                csv_writer.writerow(["Project ID", "Has CMakeLists", "Languages", "Dependencies Found", "Pinned Req. Dependencies", "Pinned Opt. Dependencies" , "Tests Found", "Uses GTest"])
            
                for row in reader:
                    if len(row) < 8:
                        continue  # Ensure the row has enough columns
                
                    entry_id     = row[3].strip()  # Column 4 (doi)
                    entry_number = row[4].strip()  # Column 5 (joss_id)
                    repo_url     = row[6].strip()  # Column 7 (html_url)
                    repo_name    = row[7].strip()  # Column 8 (repo_name)
                    
                    print(f"Crawling {entry_id} with URL {repo_url}.")
                
                    if repo_url:
                        # Clone the repository
                        repo_path = clone_repo(repo_url, "./")
                        # Find CMake files paths
                        cmake_lists_paths = find_cmake_files(repo_path)
                        # Analyse the CMake files and get the JSON format data
                        result_json = parse_cmake_files(cmake_lists_paths)
                        
                        # Generate the requirements file.
                        data = json.loads(result_json)
                        generate_cpp_requirements(list((data["dependencies"])), './' + entry_number + '_' + repo_name + '_requirements.txt')
                        
                        # Write the CSV output.
                        csv_row = generate_csv_row(result_json, entry_id)
                        csv_writer.writerow(csv_row)
            

    except FileNotFoundError:
        print(f"The file {csv_file_path} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")
        

def main() -> None:
    parser = argparse.ArgumentParser(description="Parse input CSV file, crawl (clone) and analyse CMake project and generate a CSV result.")
    parser.add_argument("--input", help="Path to the input CSV file.")
    parser.add_argument("--output", help="Path to the output CSV file.")

    args = parser.parse_args()

    process_csv_and_handle_repos(args.input, args.output)


if __name__ == "__main__":
    main()
