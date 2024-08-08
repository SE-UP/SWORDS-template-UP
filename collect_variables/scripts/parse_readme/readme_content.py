"""
Reads github repostory links from given csv file and 
fetch the README content, and stores the content in a
 new column (single cell per readme) in the CSV file.
"""

import os
import base64
import time
from urllib.parse import urlparse, unquote
import argparse
import requests
import pandas as pd
from dotenv import load_dotenv
from ghapi.all import GhApi
from requests.exceptions import HTTPError, Timeout

def handle_rate_limit(response):
    """
    Handle GitHub API rate limiting by waiting until the limit resets.
    
    Args:
        response (requests.Response): The HTTP response object.
    """
    if 'X-RateLimit-Remaining' in response.headers:
        remaining = int(response.headers['X-RateLimit-Remaining'])
        reset_time = int(response.headers['X-RateLimit-Reset'])
        if remaining == 0:
            wait_time = max(0, reset_time - time.time())
            print(f"Rate limit exceeded. Waiting for {wait_time} seconds.")
            time.sleep(wait_time + 1)  # Wait a bit longer to ensure the limit is reset

def is_github_url(url):
    """
    Check if the given URL is a GitHub URL.

    Args:
        url (str): The URL to check.

    Returns:
        bool: True if the URL is a GitHub URL, False otherwise.
    """
    return url.startswith('https://github.com')

def get_content_from_github(api, owner, repo):
    """
    Fetch the contents of a GitHub repository.

    Args:
        api (GhApi): The GitHub API client.
        owner (str): The owner of the repository.
        repo (str): The repository name.

    Returns:
        list: List of contents of the repository.
    """
    try:
        return api.repos.get_content(owner, repo, path="")
    except HTTPError as e:
        if e.response.status_code in {404, 403}:
            handle_rate_limit(e.response)
        print(f"HTTP error occurred: {e}. Skipping this repository.")
    return None

def download_readme_content(content):
    """
    Download the README content from the provided content information.

    Args:
        content (dict): The content information.

    Returns:
        str: The README content, or None if the request was unsuccessful.
    """
    if 'content' in content:
        return base64.b64decode(content.content).decode('utf-8')
    if content.download_url:
        try:
            response = requests.get(content.download_url, timeout=10)
            handle_rate_limit(response)  # Check for rate limit and wait if needed
            response.raise_for_status()
            return response.text
        except Timeout:
            print(f"Timeout when trying to download {content.download_url}")
    return None

def get_readme_content(github_url, api):
    """
    Fetch the README content of a GitHub repository.

    Args:
        github_url (str): The URL of the GitHub repository.
        api (GhApi): The GitHub API client.

    Returns:
        str: The README content, or None if the request was unsuccessful.
    """
    if not isinstance(github_url, str) or not is_github_url(github_url):
        print(f"Invalid GitHub URL: {github_url}")
        return None

    parsed_url = urlparse(unquote(github_url))
    path_parts = parsed_url.path.strip('/').split('/')
    if len(path_parts) < 2:
        print(f"Invalid GitHub URL format: {github_url}")
        return None

    owner, repo = path_parts[0], path_parts[1]
    print(f"Processing repository: {owner}/{repo} ({github_url})")

    contents = get_content_from_github(api, owner, repo)
    if contents is None:
        return None

    for content in contents:
        if content.name.lower().startswith('readme'):
            readme_content = download_readme_content(content)
            if readme_content:
                return f"README_start\n{readme_content}\nREADME_end"

    return None

def process_csv_file(input_csv, output_csv):
    """
    Process the CSV file to fetch the README content from repositories and update the CSV.

    Args:
        input_csv (str): The path to the input CSV file.
        output_csv (str): The path to the output CSV file.
    """
    script_dir = os.path.dirname(os.path.realpath(__file__))
    env_path = os.path.join(script_dir, '..', '..', '..', '.env')
    load_dotenv(dotenv_path=env_path, override=True)

    token = os.getenv('GITHUB_TOKEN')
    api = GhApi(token=token)

    chunksize = 100
    chunks = []

    for chunk in pd.read_csv(input_csv, sep=';', chunksize=chunksize):
        for i, row in chunk.iterrows():
            html_url = row.get('html_url', '')
            if isinstance(html_url, float) and pd.isna(html_url):
                html_url = ''  # Convert NaN to empty string
            html_url = str(html_url).strip()  # Convert to string and strip whitespace

            if is_github_url(html_url):
                print(f"Processing URL: {html_url}")
                readme_content = get_readme_content(html_url, api)
                if readme_content:
                    readme_content = readme_content.replace('\n', ' ')
                chunk.at[i, 'readme'] = readme_content
            else:
                print(f"Skipping non-GitHub URL: {html_url}")
                chunk.at[i, 'readme'] = None
        chunks.append(chunk)

    dataframe = pd.concat(chunks, ignore_index=True)
    dataframe.to_csv(output_csv, index=False)
    print(f"Processing complete. Updated CSV saved to {output_csv}")

if __name__ == '__main__':
    DESCRIPTION = 'Fetch and update the README content from repositories listed in a CSV file.'
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument('--input', type=str, required=True, help='The input CSV file path')
    parser.add_argument('--output', type=str, required=True, help='The output CSV file path')
    args = parser.parse_args()
    process_csv_file(args.input, args.output)
