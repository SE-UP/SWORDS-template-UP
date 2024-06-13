"""
This script checks for the presence of folders .github (github actions)
in the root
directory of GitHub repositories listed in a CSV file.
It uses the GitHub API
to access the repositories and updates the CSV file with the results.
"""

import argparse
import os
import pandas as pd
import time
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
print(f"Token: {token}")
print(f"Username: {username}")

# Use the token to create a Github instance
g = Github(token)


def check_github_actions(repo):
    try:
        contents = repo.get_contents("")
        for content in contents:
            if content.type == "dir" and content.name == ".github":
                github_contents = repo.get_contents(content.path)
                for github_content in github_contents:
                    if (github_content.type == "dir" and
                            github_content.name == "workflows"):
                        return 'github_actions'
        return None
    except GithubException as e:
        print(f"Error accessing repository: {e}")
        return None


def check_travis(repo):
    """
    Check if a GitHub repository has implemented Travis CI.

    Parameters:
    repo (github.Repository.Repository): The GitHub repository to check.

    Returns:
    bool: True if '.travis.yml' file is found, False otherwise.
    """
    try:
        repo.get_contents(".travis.yml")
        return 'travis'
    except GithubException as e:
        print(f"Error accessing repository: {e}")
        return None


def check_circleci(repo):
    """
    Check if a GitHub repository has implemented CircleCI.

    Parameters:
    repo (github.Repository.Repository): The GitHub repository to check.

    Returns:
    bool: True if '.circleci/config.yml' file is found, False otherwise.
    """
    try:
        repo.get_contents(".circleci/config.yml")
        return 'circleci'
    except GithubException as e:
        print(f"Error accessing repository: {e}")
        return None


def check_jenkins(repo):
    """
    Check if a GitHub repository has implemented Jenkins.

    Parameters:
    repo (github.Repository.Repository): The GitHub repository to check.

    Returns:
    bool: True if 'Jenkinsfile' is found, False otherwise.
    """
    try:
        repo.get_contents("Jenkinsfile")
        return 'jenkins'
    except GithubException as e:
        print(f"Error accessing repository: {e}")
        return None


def check_azure_pipelines(repo):
    """
    Check if a GitHub repository has implemented Azure Pipelines.

    Parameters:
    repo (github.Repository.Repository): The GitHub repository to check.

    Returns:
    bool: True if 'azure-pipelines.yml' file is found, False otherwise.
    """
    try:
        repo.get_contents("azure-pipelines.yml")
        return 'azure_pipelines'
    except GithubException as e:
        print(f"Error accessing repository: {e}")
        return None


def main(csv_file):
    df = pd.read_csv(csv_file, sep=';', on_bad_lines='warn')
    if 'continuous_integration' not in df.columns:
        df['continuous_integration'] = False
    if 'ci_tool' not in df.columns:
        df['ci_tool'] = None

        ci_checks = [
            check_github_actions,
            check_travis,
            check_circleci,
            check_jenkins,
            check_azure_pipelines
        ]

    count = 0
    for index, row in df.iterrows():
        url = row['html_url']
        if pd.isna(url):
            print("Skipping row with missing URL")
            continue
        print(f"Working on repository: {url}")
        repo_name = url.split('https://github.com/')[-1]
        try:
            repo = g.get_repo(repo_name)
            for ci_check in ci_checks:
                ci_tool = ci_check(repo)
                if ci_tool is not None:
                    df.loc[index, 'continuous_integration'] = True
                    df.loc[index, 'ci_tool'] = ci_tool
                    break
            count += 1
            print(f"Repositories completed: {count}")
            # Save to CSV after each repository is checked
            df.to_csv(csv_file, index=False)
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
    parser = argparse.ArgumentParser(
        description='Check for GitHub Actions in GitHub repositories.')
    parser.add_argument('csv_file', type=str, help='Input CSV file')
    args = parser.parse_args()
    main(args.csv_file)
