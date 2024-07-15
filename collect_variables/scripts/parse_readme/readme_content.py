"""
This script fetches the README content from a list of GitHub repositories provided in a CSV file.
It uses the GitHub API to fetch the README content, and stores the content in a
 new column in the CSV file.
The script handles pagination by reading the CSV file in chunks, 
and it handles rate limiting by using a GitHub token.
"""

import os
import base64
from urllib.parse import urlparse, unquote
import argparse
import requests
import pandas as pd
from dotenv import load_dotenv
from ghapi.all import GhApi
from requests.exceptions import HTTPError


def get_readme_content(github_url, api):
    """
    Fetch the README content of a GitHub repository.

    Args:
        github_url (str): The URL of the GitHub repository.
        api (GhApi): The GitHub API client.

    Returns:
        str: The README content, or None if the request was unsuccessful.
    """
    if not isinstance(github_url, str):
        print(f"Invalid GitHub URL: {github_url}")
        return None
    parsed_url = urlparse(unquote(github_url))
    path_parts = parsed_url.path.strip('/').split('/')
    if len(path_parts) < 2:
        print(f"Invalid GitHub URL: {github_url}")
        return None

    owner = path_parts[0]
    repo = path_parts[1]

    try:
        contents = api.repos.get_content(owner, repo, path="")
        for content in contents:
            if content.name.lower().startswith('readme'):
                if 'content' in content:
                    readme_content = base64.b64decode(content.content)
                    return readme_content.decode('utf-8')
                if content.download_url:
                    try:
                        url = content.download_url
                        timeout = 10
                        response = requests.get(url, timeout=timeout)
                        response.raise_for_status()
                        return response.text
                    except requests.exceptions.Timeout:
                        print(f"Timeout when trying to download {content.download_url}")
                        return None
    except HTTPError:
        print(f"Could not find content for {github_url}")

    print(f"No README found for {github_url}")
    return None


def process_csv_file(input_csv):
    """
    Process the CSV file to fetch the README content from repositories and update the CSV.

    Args:
        input_csv (str): The path to the input CSV file.
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
            readme_content = get_readme_content(row['html_url'], api)
            if readme_content:
                readme_content = readme_content.replace('\n', ' ')
            else:
                readme_content = None
            chunk.at[i, 'readme'] = readme_content
        chunks.append(chunk)

    dataframe = pd.concat(chunks, ignore_index=True)
    dataframe.to_csv(input_csv, index=False)


if __name__ == '__main__':
    description = 'Fetch and update the README content from repositories listed in a CSV file.'
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--input', type=str, required=True, help='The input CSV file path')
    args = parser.parse_args()
    process_csv_file(args.input)
