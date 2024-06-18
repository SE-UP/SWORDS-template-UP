"""
Checks test' or 'tests' directories at the root level of GitHub
repositories specified in a CSV file.
"""

import argparse
import os
import pandas as pd
from github import Github, GithubException # pylint: disable=E0611
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
print(f"Token: {token}")
print(f"Username: {username}")

# Use the token to create a Github instance
github_instance = Github(token)


def check_test_folder(repo):
    """
    Check if a GitHub repository has a 'test' or
    'tests' folder in its root directory.

    Parameters:
    repo (github.Repository.Repository): The GitHub repository to check.

    Returns:
    bool: True if 'test' or 'tests' folder is found, False otherwise.
    """
    try:
        contents = repo.get_contents("")
        for content in contents:
            if content.type == "dir" and \
                    content.name.lower() in ["test", "tests"]:
                return True
        return False
    except GithubException as github_exception:
        print(f"Error accessing repository: {github_exception}")
        return False


def main(csv_file):
    """
    Main function to read the CSV file, check the repositories,
      and update the CSV file.

    Parameters:
    csv_file (str): The path to the CSV file.
    """
    data_frame = pd.read_csv(csv_file, sep=';', on_bad_lines='warn')
    if 'test_folder' not in data_frame.columns:
        data_frame['test_folder'] = False

    count = 0
    for url in data_frame['html_url']:
        if pd.isna(url):
            print("Skipping row with missing URL")
            continue
        print(f"Working on repository: {url}")
        repo_name = url.split('https://github.com/')[-1]
        try:
            repo = github_instance.get_repo(repo_name)
            data_frame.loc[data_frame['html_url'] == url, 'test_folder'] = \
                check_test_folder(repo)
            count += 1
            print(f"Repositories completed: {count}")
        except GithubException as github_exception:
            print(f"Error accessing repository {repo_name}: {github_exception}")
            continue

    data_frame.to_csv(csv_file, index=False)


if __name__ == "__main__":
    argument_parser = argparse.ArgumentParser(
        description='Check for test folders in GitHub repositories.')
    argument_parser.add_argument('csv_file', type=str, help='Input CSV file')
    arguments = argument_parser.parse_args()
    main(arguments.csv_file)
