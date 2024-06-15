'''
This program checks the presence of comments at the start of
source code files in GitHub repositories.
'''
import os
import argparse
from urllib.parse import urlparse
import pandas as pd
import requests
from dotenv import load_dotenv

# Get the directory of the current script
script_dir = os.path.dirname(os.path.realpath(__file__))

# Create the relative path to the .env file
env_path = os.path.join(script_dir, '..', '..', '..', '.env')

# Load the .env file
load_dotenv(dotenv_path=env_path, override=True)

# Get the GITHUB_TOKEN from the .env file
token = os.getenv('GITHUB_TOKEN')

REQUEST_TIMEOUT = 10  # Timeout for requests.get in seconds

def fetch_repository_files(url, headers):
    """
    Fetches the list of source code files from a GitHub repository recursively.

    Args:
        url (str): The GitHub repository URL.
        headers (dict): The headers for GitHub API requests.

    Returns:
        list: A list of URLs of the source code files.
    """
    repo_files = []
    repo_url_parts = urlparse(url)
    owner, repo = repo_url_parts.path.strip('/').split('/')[:2]
    api_url = f'https://api.github.com/repos/{owner}/{repo}/contents'

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
        if len(lines) > 0:
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


def analyze_repositories(input_csv):
    """
    Analyzes GitHub repositories for comments at the start of files.

    Args:
        input_csv (str): Input CSV file containing repository URLs i
        n "html_url" column.

    The function updates the input CSV file with two new columns:
    'comment_percentage' - The percentage of files in the repository
    that start with a comment.
    'comment_category' - Categorical representation of 'comment_percentage'.
    Can be 'none', 'some', 'more', or 'most'.
    """
    headers = {'Authorization': f'token {token}'}
    # pylint: disable=invalid-name
    df = pd.read_csv(input_csv, sep=',', on_bad_lines='warn')
    # Filter the DataFrame based on the 'language' column
    # pylint: disable=invalid-name
    df = df[df['language'].isin(['Python', 'R', 'C++'])]
    total_repos = len(df)

    if 'comment_percentage' not in df.columns:
        df['comment_percentage'] = 0
    if 'comment_category' not in df.columns:
        df['comment_category'] = ''

    for index, row in df.iterrows():
        repo_url = row['html_url']

        print(f"Processing repository {index+1}/{total_repos}: {repo_url}")
        try:
            repo_files = fetch_repository_files(repo_url, headers)
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
            df.to_csv(input_csv, index=False)
        # pylint: disable=broad-except
        except Exception as error:
            print(f"Error processing repository {repo_url}: {error}")


if __name__ == '__main__':
    DESC = 'Analyze GitHub repositories for comments at start of files.'
    parser = argparse.ArgumentParser(description=DESC)
    parser.add_argument(
        'input_csv',
        help='Input CSV file containing repository URLs in "html_url" column'
    )
    args = parser.parse_args()

    analyze_repositories(args.input_csv)
