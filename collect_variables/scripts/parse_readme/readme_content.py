import argparse
from dotenv import load_dotenv
from ghapi.all import GhApi
import requests
import os
from urllib.parse import urlparse, unquote
import base64
import pandas as pd
from fastcore.net import HTTP404NotFoundError


def get_readme_content(github_url, api):
    """
    Fetch the README content of a GitHub repository.

    Args:
        github_url (str): The URL of the GitHub repository.

    Returns:
        str: The README content, or None if the request was unsuccessful.
    """
    # Check if github_url is a string
    if not isinstance(github_url, str):
        print(f"Invalid GitHub URL: {github_url}")
        return None

    # Parse the URL and unquote to handle URLs with special characters
    parsed_url = urlparse(unquote(github_url))
    path_parts = parsed_url.path.strip('/').split('/')
    
    # Check if path_parts has at least two elements
    if len(path_parts) < 2:
        print(f"Invalid GitHub URL: {github_url}")
        return None

    # The first part of the path is the owner, and the second part is the repo
    owner = path_parts[0]
    repo = path_parts[1]

    try:
        # Fetch the repository's root directory content
        contents = api.repos.get_content(owner, repo, path="")
        for content in contents:
            # Check if the content name starts with 'README' or 'readme'
            if content.name.lower().startswith('readme'):
                # Check if the content attribute exists
                if 'content' in content:
                    # Decode the content from base64
                    readme_content = base64.b64decode(content.content).decode('utf-8')
                    return readme_content
                elif content.download_url:  # Check if download_url is not None
                    # If the content attribute does not exist, download the file from the download_url
                    try:
                        response = requests.get(content.download_url, timeout=10)
                        response.raise_for_status()
                        return response.text
                    except requests.exceptions.Timeout:
                        print(f"Timeout when trying to download {content.download_url}")
                        return None
    except HTTP404NotFoundError:
        print(f"Could not find content for {github_url}")
        return None

    print(f"No README found for {github_url}")
    return None

def main():
    """
    Main function that accepts a CSV file path, reads the 'html_url' column, fetches the README content for each URL,
    and saves the content to a new 'readme' column.
    """
    # Set up command-line argument parsing
    parser = argparse.ArgumentParser(description='Fetch and print the README content from a GitHub repository.')
    parser.add_argument('csv_file', type=str, help='The CSV file path')

    args = parser.parse_args()

    # Get the directory of the current script
    script_dir = os.path.dirname(os.path.realpath(__file__))

    # Create the relative path to the .env file
    env_path = os.path.join(script_dir, '..', '..', '..', '.env')

    # Load the .env file
    load_dotenv(dotenv_path=env_path, override=True)

    # Get the GITHUB_TOKEN from the .env file
    token = os.getenv('GITHUB_TOKEN')

    # Initialize the GitHub API client with the token
    api = GhApi(token=token)

    # Read the CSV file
    df = pd.read_csv(args.csv_file)

    # Fetch README content for each URL and save it to the 'readme' column
    for i, row in df.iterrows():
        df.at[i, 'readme'] = get_readme_content(row['html_url'], api)
        # Save the DataFrame back to the CSV file after each row is processed
        df.to_csv(args.csv_file, index=False)

if __name__ == '__main__':
    main()