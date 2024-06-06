#!/usr/bin/env python3
"""
This script retrieves the GitHub token from a .env file.
The .env file is assumed to be located three directories up from the script's directory.
It then reads a CSV file, fetches the readme content of each GitHub repository listed in the file,
and writes the readme content to a new column in the DataFrame.
The updated DataFrame is written to an output CSV file.
"""

import os
import argparse
import pandas as pd
from dotenv import load_dotenv
from ghapi.all import GhApi

def get_readme_content(url, token):
    """
    Fetch the readme content of a GitHub repository.

    Args:
        url (str): The URL of the GitHub repository.
        token (str): The GitHub token.

    Returns:
        str: The readme content, or None if the request was unsuccessful.
    """
    repo = url.split("github.com/")[-1]
    owner, repo = repo.split('/', 1)
    api = GhApi(token)
    print(token)
    try:
        readme = api.repos.get_readme(owner, repo)
        return readme.text
    except Exception as e:
        print(f"Failed to fetch readme for {url}. Error: {e}")
        return None

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", "-i", help="The file name of the input CSV", default="input.csv")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.realpath(__file__))
    env_path = os.path.join(script_dir, '..', '..', '..', '.env')
    load_dotenv(dotenv_path=env_path, override=True)
    token = os.getenv('GITHUB_TOKEN')

    df = pd.read_csv(args.input, sep=";")
    for index, row in df.iterrows():
        print(f"Processing repository: {row['html_url']}")
        row['readme'] = get_readme_content(row['html_url'], token)
        row.to_frame().T.to_csv('output.csv', mode='a' if index > 0 else 'w', index=False)
    df.dropna(inplace=True)