"""
This script extracts metadata from GitHub repositories listed in a CSV file.
It uses the GitHub API to fetch information such as stars, forks, issues,
contributors, and download counts for each repository. The input and output CSV
file paths are specified using command-line arguments. The script handles
pagination for contributors, manages API rate limits, and outputs the results
to a specified CSV file.

Dependencies:
- pandas
- ghapi
- python-dotenv
- argparse
- chardet

The script manages API rate limit errors (HTTP 403) by waiting until the rate 
limit is reset before retrying. If it cannot fetch data for some URLs, it leaves 
the metadata fields empty while keeping the original data intact.
"""

import os
import time
import json #construct url and parse object eg: https://api.github.com/repos/SE-UP/SWORDS-template-UP/languages
import argparse
from urllib.error import HTTPError
import pandas as pd
import chardet  
from dotenv import load_dotenv
from ghapi.all import GhApi

# Load GitHub token from .env file
script_dir = os.path.dirname(os.path.realpath(__file__))
env_path = os.path.join(script_dir, '..', '..', '..', '.env')
load_dotenv(dotenv_path=env_path, override=True)
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')

# Check if the GitHub token is loaded
if not GITHUB_TOKEN:
    raise ValueError('GitHub token not found. Please set GITHUB_TOKEN in the .env file.')

# Initialize the GitHub API client
api = GhApi(token=GITHUB_TOKEN)


def detect_encoding(file_path):
    """
    Detects the encoding of a file using chardet.

    Args:
        file_path (str): The path to the file.

    Returns:
        str: The detected encoding.
    """
    with open(file_path, 'rb') as file:
        result = chardet.detect(file.read())
        encoding = result['encoding']
        print(f"Detected file encoding: {encoding}")
        return encoding


def handle_rate_limit():
    """
    Handles the GitHub API rate limit by sleeping for 15 minutes when the limit
    is reached.
    """
    print('API rate limit exceeded. Sleeping for 15 minutes...')
    time.sleep(15 * 60)  # Sleep for 15 minutes


def is_rate_limit_error(error):
    """
    Returns True when the exception represents a GitHub API rate limit response.
    """
    code = getattr(error, 'code', None)
    msg = str(error).lower()
    return code == 403 and 'rate limit' in msg

def get_repo_languages_json(owner, repo_name):
    """
    Fetch languages for a repo and return them as a JSON dict string:
    e.g. {"Python": 72.4, "C": 19.6}
    Values are percentages (0-100).
    """
    try:
        lang_bytes = api.repos.list_languages(owner, repo_name)  # dict {lang: bytes}
        if not lang_bytes:
            return json.dumps({})

        total = sum(lang_bytes.values())
        if total == 0:
            return json.dumps({})

        lang_percent = {
            lang: round((bytes_count / total) * 100, 2)
            for lang, bytes_count in lang_bytes.items()
        }

        # Optional: sort keys by percentage descending (to keep output readable)
        lang_percent = dict(sorted(lang_percent.items(), key=lambda x: x[1], reverse=True))

        return json.dumps(lang_percent)

    except Exception as e:
        print(f"Error fetching languages for {owner}/{repo_name}: {e}")
        return json.dumps({})

def get_repo_metadata(repo_url):
    """
    Extracts metadata from a GitHub repository URL, including contributors and
    download counts.

    Args:
        repo_url (str): The URL of the GitHub repository.

    Returns:
        dict: A dictionary containing repository metadata.
    """
    try:
        print(f'Processing URL: {repo_url}')
        # Extract the owner and repo name from the URL
        parts = repo_url.strip('/').split('/')
        owner = parts[-2]
        repo_name = parts[-1]

        # Fetch repository data using GitHub API
        repo_data = api.repos.get(owner, repo_name)

        #fetch all languages & % JSON object(eg. https://api.github.com/repos/SE-UP/SWORDS-template-UP/languages)
        languages_json = get_repo_languages_json(owner, repo_name)


        # Fetch contributors with pagination handling
        contributors = []
        page = 1
        while True:
            contrib_page = api.repos.list_contributors(owner, repo_name, per_page=100, page=page)
            if not contrib_page:
                break
            contributors.extend(contrib_page)
            page += 1

        # Extract contributor usernames and their contribution counts
        contributor_list = ', '.join(
            [f'{contrib.login} ({contrib.contributions} contributions)'
             for contrib in contributors]
        )

        # Get number of contributors
        num_contributors = len(contributors)

        # Fetch releases for download counts
        try:
            releases = api.repos.list_releases(owner, repo_name)
            total_downloads = sum(asset.download_count
                                  for release in releases
                                  for asset in release.assets)
        except Exception as download_error:
            print(f'Error fetching downloads: {download_error}')
            total_downloads = 'N/A'

        # Extract relevant metadata
        return {
            'html_url': repo_url,  # Use 'html_url' as the key for merging
            'Repository Name': repo_data.name,
            'Full Name': repo_data.full_name,
            'Description': repo_data.description or 'N/A',
            'Stars': repo_data.stargazers_count,
            'Forks': repo_data.forks_count,
            'Issues': repo_data.open_issues_count,
            'Watchers': repo_data.watchers_count,
            'Language': repo_data.language or 'N/A',
            'languages_json': languages_json,
            'License': repo_data.license['name'] if repo_data.license else 'N/A',
            'Created Date': repo_data.created_at,
            'Updated Date': repo_data.updated_at,
            'Pushed Date': repo_data.pushed_at,
            'Default Branch': repo_data.default_branch,
            'Size': repo_data.size,
            'Contributors': contributor_list or 'No contributors found',
            'Number of Contributors': num_contributors,
            'Total Downloads': total_downloads
        }

    except HTTPError as http_error:
        if is_rate_limit_error(http_error):
            print(f'Rate limit hit while processing {repo_url}: {http_error}')
            handle_rate_limit()
            return get_repo_metadata(repo_url)

        if http_error.code == 404:
            print(f'Repository not found or inaccessible, skipping {repo_url}')
            return None

        if http_error.code == 403:
            print(f'GitHub access forbidden for {repo_url}: {http_error}')
            return None

        print(f'HTTP error processing {repo_url}: {http_error}')
        return None

    except Exception as other_error:
        print(f'Error processing {repo_url}: {other_error}')
        return None  # Return None if there are other errors


def main(input_csv_path, output_csv_path):
    """
    Main function to read input CSV, extract metadata, and save to output CSV.

    Args:
        input_csv_path (str): Path to the input CSV file with GitHub URLs.
        output_csv_path (str): Path to the output CSV file.
    """
    print('Script started.')

    # Detect file encoding
    encoding = detect_encoding(input_csv_path)

    # Try reading the input CSV file with detected encoding and comma delimiter
    try:
        input_df = pd.read_csv(input_csv_path, encoding=encoding, delimiter=',', on_bad_lines='skip')
    except Exception as error:
        print(f'Failed to read the CSV file: {error}')
        return

    # Print out the columns to debug
    print("Columns in the original DataFrame (input_df):", input_df.columns)

    # List to store metadata dictionaries
    metadata_list = []

    # Iterate through URLs in the DataFrame, drop NaN values
    for idx, url in input_df['html_url'].dropna().items():
        # Ensure the URL is a string and check if it's a GitHub URL
        if isinstance(url, str) and 'github.com' in url:
            metadata = get_repo_metadata(url)
            if metadata:
                metadata_list.append(metadata)
        else:
            print(f'Skipping invalid or non-GitHub URL at row {idx}: {url}')

    # Create a DataFrame for the new metadata
    metadata_df = pd.DataFrame(metadata_list)

    # Print out the columns in the metadata DataFrame to debug
    print("Columns in the metadata DataFrame (metadata_df):", metadata_df.columns)

    # Merge the original dataframe with the new metadata based on 'html_url'
    merged_df = pd.merge(input_df, metadata_df, on='html_url', how='left')

    # Save the merged data to a new CSV file
    merged_df.to_csv(output_csv_path, index=False)

    print(f'Metadata extraction complete. Saved to {output_csv_path}')
    print('Script ended.')


if __name__ == '__main__':
    # Setup argument parser
    parser = argparse.ArgumentParser(
        description='Extract metadata from GitHub repository URLs in a CSV file.'
    )
    parser.add_argument('--input', type=str, required=True,
                        help='Path to the input CSV file containing GitHub URLs.')
    parser.add_argument('--output', type=str, default='output.csv',
                        help='Path to the output CSV file.')

    # Parse arguments
    args = parser.parse_args()

    # Run the main function
    main(args.input, args.output)
