
"""
This script processes a CSV file containing GitHub repository URLs. 
For each repository with GitHub Actions enabled, it scans the YAML files in the 
.github/workflows directory to detect the presence of specific testing libraries
and linters for Python, R, and C++. The findings are recorded in the 
'add_test_rule' and 'add_lint_rule' columns of the CSV file.

To manage GitHub API rate limits, the script pauses execution until the rate 
limit resets. Repositories with existing values (True or False) in the 
'add_test_rule' and 'add_lint_rule' columns are skipped.
"""

import os
import re
import time
import argparse
import pandas as pd
# pylint: disable=E0611
from github import Github, GithubException, RateLimitExceededException
from dotenv import load_dotenv

# Get the directory of the current script
script_dir = os.path.dirname(os.path.realpath(__file__))

# Create the relative path to the .env file
env_path = os.path.join(script_dir, '..', '..', '..', '.env')

# Load the .env file
load_dotenv(dotenv_path=env_path, override=True)

# Get the GITHUB_TOKEN and GITHUB_USERNAME from the .env file
token = os.getenv('GITHUB_TOKEN')
username = os.getenv('GITHUB_USERNAME')

# Use the token to create a Github instance
g = Github(token)

# Testing libraries for different languages
testing_libraries = {
    'python': ['unittest', 'pytest', 'nose'],
    'r': ['testthat'],
    'cpp': ['gtest']
}

# Linters for different languages
linters = {
    'python': ['pylint', 'flake8', 'pycodestyle'],
    'r': ['lintr'],
    'cpp': ['cpplint']
}

def get_all_files(repo, path):
    """
    Recursively get all files in a given repository path.

    Parameters:
    repo (github.Repository.Repository): The repository.
    path (str): The path in the repository.

    Returns:
    list: A list of all files in the path.
    """
    contents = []
    try:
        repo_contents = repo.get_contents(path)
        for content in repo_contents:
            if content.type == 'dir':
                contents.extend(get_all_files(repo, content.path))
            else:
                contents.append(content)
    except GithubException as exception:
        print(f"Error accessing path {path} in repository {repo.full_name}: {exception}")
    return contents

def check_testing_libraries(file_content, language):
    """
    Check if a YAML file contains any of the testing libraries
    for a given language.

    Parameters:
    file_content (str): The content of the YAML file.
    language (str): The programming language.

    Returns:
    bool: True if any testing library is found, False otherwise.
    """
    for library in testing_libraries[language]:
        if re.search(r'\b' + re.escape(library) + r'\b', file_content):
            return True
    return False

def check_linters(file_content, language):
    """
    Check if a YAML file contains any of the linters for a given language.

    Parameters:
    file_content (str): The content of the YAML file.
    language (str): The programming language.

    Returns:
    bool: True if any linter is found, False otherwise.
    """
    for linter in linters[language]:
        if re.search(r'\b' + re.escape(linter) + r'\b', file_content):
            return True
    return False

def process_repository(repo_name, index, data_frame, csv_file):
    """
    Process a single repository to check for testing libraries and linters.

    Parameters:
    repo_name (str): The repository name.
    index (int): The index of the row in the DataFrame.
    data_frame (pd.DataFrame): The DataFrame being processed.
    csv_file (str): The path to the CSV file.

    Returns:
    int: The updated count of processed repositories.
    """
    repo = g.get_repo(repo_name)
    paths = [".github"]
    for path in paths:
        contents = get_all_files(repo, path)
        for content in contents:
            if content.name.endswith('.yml') or content.name.endswith('.yaml'):
                file_content = content.decoded_content.decode()
                if pd.isna(data_frame.loc[index, 'add_test_rule']):
                    data_frame.loc[index, 'add_test_rule'] = check_testing_libraries(file_content,
                                                                                      'python')
                if pd.isna(data_frame.loc[index, 'add_lint_rule']):
                    data_frame.loc[index, 'add_lint_rule'] = check_linters(file_content, 'python')
    # Check for .travis.yml in the root directory
    try:
        travis_file = repo.get_contents(".travis.yml")
        file_content = travis_file.decoded_content.decode()
        if pd.isna(data_frame.loc[index, 'add_test_rule']):
            data_frame.loc[index, 'add_test_rule'] = check_testing_libraries(file_content, 'python')
        if pd.isna(data_frame.loc[index, 'add_lint_rule']):
            data_frame.loc[index, 'add_lint_rule'] = check_linters(file_content, 'python')
    except GithubException:
        print(f"No .travis.yml file found in repository {repo_name}")
    # Save to CSV after each repository is checked
    data_frame.to_csv(csv_file, index=False)
    return 1

def main(input_csv, output_csv):
    """
    Main function that reads the CSV file and checks each repository for
    testing libraries and linters.

    Parameters:
    input_csv (str): Path to the input CSV file.
    output_csv (str): Path to the output CSV file.

    Returns:
    None
    """
    data_frame = pd.read_csv(input_csv, sep=',', on_bad_lines='warn')
    if 'add_lint_rule' not in data_frame.columns:
        data_frame['add_lint_rule'] = None
    if 'add_test_rule' not in data_frame.columns:
        data_frame['add_test_rule'] = None

    count = 0
    for index, row in data_frame.iterrows():
        url = row['html_url']
        if pd.isna(url):
            print("Skipping row with missing URL")
            continue
        if pd.isna(row['ci_tool']):
            print(f"Skipping repository {url} without CI tool")
            continue
        if not pd.isna(row['add_test_rule']) or not pd.isna(row['add_lint_rule']):
            print(f"Skipping repository {url} with existing test or lint rule")
            continue
        print(f"Working on repository: {url}")
        repo_name = url.split('https://github.com/')[-1]
        try:
            count += process_repository(repo_name, index, data_frame, output_csv)
            print(f"Repositories completed: {count}")
        except RateLimitExceededException as exception:  # pylint: disable=unused-variable
            print("Rate limit exceeded. Sleeping until reset...")
            reset_time = g.rate_limiting_resettime
            sleep_time = reset_time - int(time.time())
            if sleep_time > 0:
                time.sleep(sleep_time)
            continue
        except GithubException:
            print(f"Error accessing repository {repo_name}")
            continue

if __name__ == "__main__":
    DESCRIPTION = 'Check for testing libraries and linters in repositories.'
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument('--input', type=str,
                        default='../collect_repositories/results/repositories_filtered.csv',
                        help='Input CSV file')
    parser.add_argument('--output', type=str, default='results/soft_dev_pract.csv',
                        help='Output CSV file')
    args = parser.parse_args()
    main(args.input, args.output)
