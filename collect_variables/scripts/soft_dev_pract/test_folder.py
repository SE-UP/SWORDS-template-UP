"""
Checks 'test' or 'tests' directories at the root level of GitHub
repositories specified in a CSV file.
"""

import os
import time
import argparse
import pandas as pd
from github import Github, GithubException, RateLimitExceededException  # pylint: disable=E0611
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
github_instance = Github(token)


def is_github_url(url):
    """
    Check if the given URL is a GitHub URL.

    Parameters:
    url (str): The URL to check.

    Returns:
    bool: True if the URL is a GitHub URL, False otherwise.
    """
    return url.startswith('https://github.com')


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
            if content.type == "dir" and content.name.lower() in ["test", "tests"]:
                return True
        return False
    except GithubException as github_exception:
        print(f"Error accessing repository: {github_exception}")
        return False


def handle_rate_limit():
    """
    Handle GitHub API rate limiting by waiting until the limit resets.

    Parameters:
    github_instance (Github): The GitHub instance to check rate limits.
    """
    rate_limit = github_instance.get_rate_limit().core
    if rate_limit.remaining == 0:
        reset_timestamp = rate_limit.reset.timestamp()
        sleep_time = max(0, reset_timestamp - time.time())
        print(f"Rate limit exceeded. Waiting for {sleep_time} seconds.")
        time.sleep(sleep_time + 1)  # Sleep until rate limit is reset


def main(input_csv, output_csv):
    """
    Main function to read the CSV file, check the repositories,
    and update the CSV file.

    Parameters:
    input_csv (str): The path to the input CSV file.
    output_csv (str): The path to the output CSV file.
    """
    data_frame = pd.read_csv(input_csv, sep=';', encoding='ISO-8859-1', on_bad_lines='warn')
    if 'test_folder' not in data_frame.columns:
        data_frame['test_folder'] = False

    count = 0
    for index, row in data_frame.iterrows():
        url = row['html_url']
        if pd.isna(url):
            print("Skipping row with missing URL")
            continue

        if not is_github_url(url):
            print(f"Skipping non-GitHub URL: {url}")
            continue

        print(f"Working on repository: {url}")
        repo_name = url.split('https://github.com/')[-1]
        try:
            handle_rate_limit()
            repo = github_instance.get_repo(repo_name)
            data_frame.loc[index, 'test_folder'] = check_test_folder(repo)
            count += 1
            print(f"Repositories completed: {count}")
        except RateLimitExceededException:
            handle_rate_limit()
            continue
        except GithubException as github_exception:
            print(f"Error accessing repository {repo_name}: {github_exception}")
            continue

    data_frame.to_csv(output_csv, index=False)


if __name__ == "__main__":
    DESCRIPTION = 'Check for test folders in GitHub repositories.'
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument('--input', type=str,
                        default='../collect_repositories/results/repositories_filtered.csv',
                        help='Input CSV file')
    parser.add_argument('--output', type=str, default='results/soft_dev_pract.csv',
                        help='Output CSV file')
    args = parser.parse_args()
    main(args.input, args.output)
