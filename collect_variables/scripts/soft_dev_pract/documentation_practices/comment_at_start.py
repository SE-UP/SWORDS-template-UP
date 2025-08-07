"""
This program checks the presence of brief comments at the start of
source code files in GitHub repositories.
"""

import os
import time
import logging
import argparse
import pandas as pd
import requests
from dotenv import load_dotenv
from requests.exceptions import HTTPError
from ghapi.all import GhApi

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Get the directory of the current script
script_dir = os.path.dirname(os.path.realpath(__file__))

# Create the relative path to the .env file
env_path = os.path.join(script_dir, '..', '..', '..','..', '.env')

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

    def get_files(url):
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
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
            logging.error(
                "Failed to fetch files from %s: %s - %s",
                url,
                response.status_code,
                response.text,
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
            return any(first_line.startswith(prefix) for prefix in prefixes)
    else:
        logging.error(
            "Failed to fetch file %s: %s - %s",
            file_url,
            response.status_code,
            response.text,
        )

    return False


def determine_comment_category(percentage):
    """Determine the comment category based on the percentage."""
    if percentage > 75:
        return 'most'
    if 50 < percentage <= 75:
        return 'more'
    if 25 < percentage <= 50:
        return 'some'
    return 'none'


def process_repository(repo_url, headers):
    """Processes a single repository for analysis."""
    repo_name = repo_url.split('https://github.com/')[-1]
    owner, repo = repo_name.split('/')

    # Handle GitHub rate limit
    rate_limit = api.rate_limit.get()
    if rate_limit['resources']['core']['remaining'] == 0:
        logging.info("Rate limit exceeded. Sleeping for %d minutes.", RATE_LIMIT_SLEEP_TIME / 60)
        time.sleep(RATE_LIMIT_SLEEP_TIME)

    # Fetch the programming language of the repository
    repo_info = api.repos.get(owner, repo)
    language = repo_info.language

    if language not in ['Python', 'R', 'C++']:
        logging.info("Skipping repository %s due to unsupported language: %s", repo_name, language)
        return None, None

    repo_files = fetch_repository_files(repo_name, headers)
    total_files = len(repo_files)
    commented_files = sum(
        check_comment_at_start(file_url, headers)
        for file_url in repo_files
    )

    comment_percentage = (commented_files / total_files) * 100 if total_files > 0 else 0
    comment_category = determine_comment_category(comment_percentage)

    return comment_percentage, comment_category

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
    data_frame = pd.read_csv(input_csv, sep=';', encoding='ISO-8859-1', on_bad_lines='warn')
    total_repos = len(data_frame)

    if 'comment_percentage' not in data_frame.columns:
        data_frame['comment_percentage'] = 0
    if 'comment_category' not in data_frame.columns:
        data_frame['comment_category'] = ''

    for index, row in data_frame.iterrows():
        repo_url = row['html_url']

        # Skip rows with missing or non-string URLs
        if not isinstance(repo_url, str) or not repo_url.startswith('https://github.com/'):
            logging.warning("Skipping non-GitHub or invalid URL: %s", repo_url)
            continue

        logging.info("Processing repository %d/%d: %s", index + 1, total_repos, repo_url)
        try:
            comment_percentage, comment_category = process_repository(repo_url, headers)
            if comment_percentage is not None and comment_category is not None:
                data_frame.at[index, 'comment_percentage'] = comment_percentage
                data_frame.at[index, 'comment_category'] = comment_category

            # Save progress to output CSV
            data_frame.to_csv(output_csv, index=False)
        except HTTPError as http_err:
            logging.error("HTTP error occurred for repository %s: %s", repo_url, http_err)
        except Exception as error:
            logging.error("Error processing repository %s: %s", repo_url, error)
            continue

    # Save the final data frame to the output CSV file
    data_frame.to_csv(output_csv, index=False)


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
