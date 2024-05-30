"""
This script reads a CSV file containing GitHub repository URLs. 
For each repository that has GitHub Actions enabled, it checks the YAML files in the .github/workflows directory 
for the presence of certain testing libraries and linters for Python, R, and C++. 
The results are written back to the CSV file in the 'add_test_rule' and 'add_lint_rule' columns. 
The script handles the GitHub API rate limit by sleeping until the rate limit resets.
If the 'add_test_rule' and 'add_lint_rule' columns already have a value (True or False), the repository is skipped.
"""

import os
import pandas as pd
from github import Github, GithubException, RateLimitExceededException
from dotenv import load_dotenv
import yaml
import argparse

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
g = Github(token)

# Testing libraries for different languages
testing_libraries = {
    'python': ['unittest', 'pytest', 'nose'],
    'r': ['testthat'],
    'cpp': ['gtest']
}

# Linters for different languages
linters = {
    'python': ['pylint', 'flake8'],
    'r': ['lintr'],
    'cpp': ['cpplint']
}

def check_testing_libraries(file_content, language):
    """
    Check if a YAML file contains any of the testing libraries for a given language.

    Parameters:
    file_content (str): The content of the YAML file.
    language (str): The programming language.

    Returns:
    bool: True if any testing library is found, False otherwise.
    """
    for library in testing_libraries[language]:
        if library in file_content:
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
        if linter in file_content:
            return True
    return False

def main(csv_file):
    df = pd.read_csv(csv_file)
    if 'add_lint_rule' not in df.columns:
        df['add_lint_rule'] = None
    if 'add_test_rule' not in df.columns:
        df['add_test_rule'] = None

    count = 0
    for index, row in df.iterrows():
        url = row['html_url']
        if pd.isna(url):
            print("Skipping row with missing URL")
            continue
        if row['github_actions'] != True:
            print(f"Skipping repository {url} without GitHub Actions")
            continue
        if not pd.isna(row['add_test_rule']) or not pd.isna(row['add_lint_rule']):
            print(f"Skipping repository {url} with existing test or lint rule")
            continue
        print(f"Working on repository: {url}")
        repo_name = url.split('https://github.com/')[-1]
        try:
            repo = g.get_repo(repo_name)
            contents = repo.get_contents(".github/workflows", ref="master")
            for content in contents:
                if content.name.endswith('.yml') or content.name.endswith('.yaml'):
                    file_content = content.decoded_content.decode()
                    df.loc[index, 'add_test_rule'] = check_testing_libraries(file_content, 'python')
                    df.loc[index, 'add_lint_rule'] = check_linters(file_content, 'python')
            count += 1
            print(f"Repositories completed: {count}")
            df.to_csv(csv_file, index=False)  # Save to CSV after each repository is checked
        except RateLimitExceededException as e:
            print("Rate limit exceeded. Sleeping until reset...")
            reset_time = g.rate_limiting_resettime
            sleep_time = reset_time - int(time.time())
            if sleep_time > 0:
                time.sleep(sleep_time)
            continue
        except GithubException as e:
            print(f"Error accessing repository {repo_name}: {e}")
            continue

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Check for testing libraries and linters in GitHub repositories.')
    parser.add_argument('csv_file', type=str, help='Input CSV file')
    args = parser.parse_args()
    main(args.csv_file)