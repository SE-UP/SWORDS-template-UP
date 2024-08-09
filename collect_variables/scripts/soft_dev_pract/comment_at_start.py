"""
This program checks the presence of brief comments at the start of
source code files in GitHub repositories.
"""

import os
import argparse
import time
from urllib.parse import urlparse
import pandas as pd
import requests
from dotenv import load_dotenv
from ghapi.all import GhApi
from requests.exceptions import HTTPError

# Get the directory of the current script
script_dir = os.path.dirname(os.path.realpath(__file__))

# Create the relative path to the .env file
env_path = os.path.join(script_dir, '..', '..', '..', '.env')

# Load the .env file
load_dotenv(dotenv_path=env_path, override=True)

# Get the GITHUB_TOKEN from the .env file
token = os.getenv('GITHUB_TOKEN')
api = GhApi(token=token)

REQUEST_TIMEOUT = 10  # Timeout for requests.get in seconds
RATE_LIMIT_SLEEP_TIME = 15 * 60  # Sleep for 15 minutes when rate limit is exceeded


def fetch_repository_files(repo_name, headers):
    """
    Fetches the list of source code files from a GitHub repository recursively.

    Args:
        repo_name (str): The GitHub repository name in the format 'owner/repo'.
        headers (dict): The headers for GitHub API requests.

    Returns:
        list: A list of URLs of the source code files.
    """
    repo_files = []
    api_url = f'https://api.github.com/repos/{repo_name}/contents'

    def get_files(api_url):
        response = requests.get(api_url, headers=headers, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            items = response.json()
            for item in items:
                if item['type'] == 'file' and (
                    item['name'].endswith('.py') or
                    item['name'].endswith('.R') or
                    item['name'].endswith('.cpp')
                ):
                    repo_files.append(item['download_url'])
                elif item['type'] == 'dir':
                    get_files(item['url'])
        else:
            print(
                f"Failed to fetch files from {api_url}: "
                f"{response.status_code} - {response.text}"
            )

    get_files(api_url)
    return repo_files


def check_comment_at_start(file_url, headers):
    """
    Checks if a file has a comment at the start.

    Args:
        file_url (str): The URL of the file to check.
        headers (dict): The headers for GitHub API requests.

    Returns:
        bool: True if the file has a comment at the start, False otherwise.
    """
    response = requests.get(file_url, headers=headers, timeout=REQUEST_TIMEOUT)
    if response.status_code == 200:
        content = response.text
        lines = content.split('\n')
        if lines:
            first_line = lines[0].strip()
            prefixes = ['#', '//', '/*', "'''", '"', "#'"]
            if any(first_line.startswith(prefix) for prefix in prefixes):
                return True
    else:
        print(
            f"Failed to fetch file {file_url}: "
            f"{response.status_code} - {response.text}"
        )
    return False


def analyze_repositories(input_csv, output_csv):
    """
    Analyzes GitHub repositories for comments at the start of files.

    Args:
        input_csv (str): Input CSV file containing repository URLs in "html_url" column.
        output_csv (str): Output CSV file to save the analysis results.

    The function updates the input CSV file with two new columns:
    'comment_percentage' - The percentage of files in the repository that start with a comment.
    'comment_category' - Categorical representation of 'comment_percentage'.
                         Can be 'none', 'some', 'more', or 'most'.
    """
    headers = {'Authorization': f'token {token}'}
    df = pd.read_csv(input_csv, sep=';', encoding='ISO-8859-1', on_bad_lines='warn')
    total_repos = len(df)

    if 'comment_percentage' not in df.columns:
        df['comment_percentage'] = 0
    if 'comment_category' not in df.columns:
        df['comment_category'] = ''

    for index, row in df.iterrows():
        repo_url = row['html_url']

        # Skip non-GitHub URLs
        if not repo_url.startswith('https://github.com/'):
            print(f"Skipping non-GitHub URL: {repo_url}")
            continue

        repo_name = repo_url.split('https://github.com/')[-1]

        try:
            # Handle GitHub rate limit
            rate_limit = api.rate_limit.get()
            if rate_limit['resources']['core']['remaining'] == 0:
                reset_time = rate_limit['resources']['core']['reset']
                sleep_time = max(0, reset_time - time.time())
                print(f"Rate limit exceeded. Sleeping for {RATE_LIMIT_SLEEP_TIME / 60} minutes.")
                time.sleep(RATE_LIMIT_SLEEP_TIME)

            # Fetch the programming language of the repository
            repo_info = api.repos.get(repo_name.split('/')[0], repo_name.split('/')[1])
            language = repo_info.language

            if language not in ['Python', 'R', 'C++']:
                print(f"Skipping repository {repo_name} due to unsupported language: {language}")
                continue

            print(f"Processing repository {index+1}/{total_repos}: {repo_url}")
            repo_files = fetch_repository_files(repo_name, headers)
            total_files = len(repo_files)
            commented_files = sum(
                check_comment_at_start(file_url, headers)
                for file_url in repo_files
            )

            if total_files > 0:
                comment_percentage = (commented_files / total_files) * 100
            else:
                comment_percentage = 0

            if comment_percentage > 75:
                comment_category = 'most'
            elif 50 < comment_percentage <= 75:
                comment_category = 'more'
            elif 25 < comment_percentage <= 50:
                comment_category = 'some'
            else:
                comment_category = 'none'

            df.loc[index, 'comment_percentage'] = comment_percentage
            df.loc[index, 'comment_category'] = comment_category

            # Save the record as soon as it is fetched
            df.to_csv(output_csv, index=False)
        except HTTPError as http_err:
            print(f"HTTP error occurred for repository {repo_url}: {http_err}")
        except Exception as error:
            print(f"Error processing repository {repo_url}: {error}")

    # Save the final dataframe to the output CSV file
    df.to_csv(output_csv, index=False)


if __name__ == '__main__':
    DESC = 'Analyze GitHub repositories for comments at start of files.'
    parser = argparse.ArgumentParser(description=DESC)
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

    analyze_repositories(args.input, args.output)
