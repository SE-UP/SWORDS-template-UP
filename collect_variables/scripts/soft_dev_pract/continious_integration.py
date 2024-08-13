"""
This script checks for the presence of folders .github (GitHub Actions)
in the root directory of GitHub repositories listed in a CSV file.
It uses the GitHub API to access the repositories and updates the CSV file with the results.
"""

import argparse
import os
import time
import pandas as pd
from github import Github, GithubException, RateLimitExceededException  # pylint: disable=E0611
from dotenv import load_dotenv

# Get the directory of the current script
script_dir = os.path.dirname(os.path.realpath(__file__))

# Create the relative path to the .env file
env_path = os.path.join(script_dir, '..', '..', '..', '.env')

# Load the .env file
load_dotenv(dotenv_path=env_path, override=True)

# Get the GITHUB_TOKEN from the .env file
token = os.getenv('GITHUB_TOKEN')

# Use the token to create a Github instance
g = Github(token)


def check_github_actions(repo):
    """
    Check if a GitHub repository has implemented GitHub Actions.

    Parameters:
    repo (github.Repository.Repository): The GitHub repository to check.

    Returns:
    str: 'github_actions' if '.github/workflows' directory is found, None otherwise.
    """
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
    except GithubException as github_exception:
        print(f"Error accessing repository: {github_exception}")
        return None


def check_travis(repo):
    """
    Check if a GitHub repository has implemented Travis CI.

    Parameters:
    repo (github.Repository.Repository): The GitHub repository to check.

    Returns:
    str: 'travis' if '.travis.yml' file is found, None otherwise.
    """
    try:
        repo.get_contents(".travis.yml")
        return 'travis'
    except GithubException as github_exception:
        print(f"Error accessing repository: {github_exception}")
        return None


def check_circleci(repo):
    """
    Check if a GitHub repository has implemented CircleCI.

    Parameters:
    repo (github.Repository.Repository): The GitHub repository to check.

    Returns:
    str: 'circleci' if '.circleci/config.yml' file is found, None otherwise.
    """
    try:
        repo.get_contents(".circleci/config.yml")
        return 'circleci'
    except GithubException as github_exception:
        print(f"Error accessing repository: {github_exception}")
        return None


def check_jenkins(repo):
    """
    Check if a GitHub repository has implemented Jenkins.

    Parameters:
    repo (github.Repository.Repository): The GitHub repository to check.

    Returns:
    str: 'jenkins' if 'Jenkinsfile' is found, None otherwise.
    """
    try:
        repo.get_contents("Jenkinsfile")
        return 'jenkins'
    except GithubException as github_exception:
        print(f"Error accessing repository: {github_exception}")
        return None


def check_azure_pipelines(repo):
    """
    Check if a GitHub repository has implemented Azure Pipelines.

    Parameters:
    repo (github.Repository.Repository): The GitHub repository to check.

    Returns:
    str: 'azure_pipelines' if 'azure-pipelines.yml' file is found, None otherwise.
    """
    try:
        repo.get_contents("azure-pipelines.yml")
        return 'azure_pipelines'
    except GithubException as github_exception:
        print(f"Error accessing repository: {github_exception}")
        return None


def handle_rate_limit_error(exception):
    """
    Handle GitHub API rate limit exceeded error by sleeping for 20 minutes.

    Parameters:
    exception (GithubException): The exception object that contains the error details.
    """
    error_message = exception.data.get("message", "")
    if "API rate limit exceeded" in error_message:
        print("Rate limit exceeded. Sleeping for 20 minutes...")
        time.sleep(20 * 60)  # Sleep for 20 minutes


def main(input_csv_file, output_csv_file):
    """
    Main function to check for continuous integration tools in GitHub repositories.

    Parameters:
    input_csv_file (str): Path to the input CSV file.
    output_csv_file (str): Path to the output CSV file.
    """
    data_frame = pd.read_csv(input_csv_file, sep=';', on_bad_lines='warn')

    if 'continuous_integration' not in data_frame.columns:
        data_frame['continuous_integration'] = False
    if 'ci_tool' not in data_frame.columns:
        data_frame['ci_tool'] = None

    ci_checks = [
        check_github_actions,
        check_travis,
        check_circleci,
        check_jenkins,
        check_azure_pipelines
    ]

    count = 0
    for index, row in data_frame.iterrows():
        url = row['html_url']
        
        # Skip empty or null URLs
        if pd.isna(url) or not url.strip():
            print(f"Skipping row with missing or null URL at index {index}")
            continue

        # Process only GitHub URLs
        if not url.startswith('https://github.com/'):
            print(f"Skipping non-GitHub URL: {url}")
            continue

        print(f"Working on repository: {url}")
        repo_name = url.split('https://github.com/')[-1]
        try:
            repo = g.get_repo(repo_name)
            for ci_check in ci_checks:
                ci_tool = ci_check(repo)
                if ci_tool is not None:
                    data_frame.loc[index, 'continuous_integration'] = True
                    data_frame.loc[index, 'ci_tool'] = ci_tool
                    break
            count += 1
            print(f"Repositories completed: {count}")
            # Save to CSV after each repository is checked
            data_frame.to_csv(output_csv_file, index=False)
        except GithubException as github_exception:
            handle_rate_limit_error(github_exception)
            print(f"Error accessing repository {repo_name}: {github_exception}")
            continue

    # Save the final dataframe to the output CSV file
    data_frame.to_csv(output_csv_file, index=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Check for CI tools in GitHub repositories.')
    parser.add_argument(
        '--input',
        default='../collect_repositories/results/repositories_filtered.csv',
        help='Input CSV file containing repository URLs in "html_url" column'
    )
    parser.add_argument(
        '--output',
        default='results/soft_dev_pract.csv',
        help='Output CSV file to save the analysis results'
    )
    args = parser.parse_args()

    main(args.input, args.output)
