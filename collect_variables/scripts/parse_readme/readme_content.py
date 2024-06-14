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
                    readme_content = base64.b64decode(content.content)
                    readme_content = readme_content.decode('utf-8')
                    return readme_content
                # Check if download_url is not None
                elif content.download_url:
                    # If the content attribute does not exist,
                    # download the file from the download_url
                    try:
                        url = content.download_url
                        timeout = 10
                        response = requests.get(url, timeout=timeout)
                        response.raise_for_status()
                        return response.text
                    except requests.exceptions.Timeout:
                        print(
                            f"Timeout when trying to download "
                            f"{content.download_url}"
                        )
                        return None
    except HTTP404NotFoundError:
        print(f"Could not find content for {github_url}")
        return None

    print(f"No README found for {github_url}")
    return None


def main():
    # Set up command-line argument parsing
    description = 'Fetch and print the README content from repository.'
    parser = argparse.ArgumentParser(description=description)
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

    # Define chunk size
    chunksize = 100

    # Create a list to store the chunks
    chunks = []

    # Read the CSV file in chunks
    for chunk in pd.read_csv(args.csv_file, sep=';', chunksize=chunksize):
        # Fetch README content for each URL and save it to the 'readme' column
        for i, row in chunk.iterrows():
            readme_content = get_readme_content(row['html_url'], api)
            # Replace newline characters with a space
            if readme_content:
                readme_content = readme_content.replace('\n', ' ')
            else:
                readme_content = None
            chunk.at[i, 'readme'] = readme_content

        # Append the chunk to the list
        chunks.append(chunk)

    # Concatenate all chunks into a single DataFrame
    df = pd.concat(chunks, ignore_index=True)

    # Save the DataFrame to the CSV file
    df.to_csv(args.csv_file, index=False)


if __name__ == '__main__':
    main()
