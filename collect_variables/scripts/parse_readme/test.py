import argparse
from dotenv import load_dotenv
from ghapi.all import GhApi
import os
from urllib.parse import urlparse, unquote
import base64

def get_readme_content(github_url):
    """
    Fetch the README content of a GitHub repository.

    Args:
        github_url (str): The URL of the GitHub repository.

    Returns:
        str: The README content, or None if the request was unsuccessful.
    """
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

    # Parse the URL and unquote to handle URLs with special characters
    parsed_url = urlparse(unquote(github_url))
    path_parts = parsed_url.path.strip('/').split('/')
    
    # The first part of the path is the owner, and the second part is the repo
    owner = path_parts[0]
    repo = path_parts[1]

    try:
        # Fetch the README file from the repository
        readme = api.repos.get_content(owner, repo, path='README.md')
        # Decode the content from base64
        readme_content = base64.b64decode(readme.content).decode('utf-8')
        return readme_content
    except Exception as e:
        print(f"Error fetching README.md for {github_url}: {e}")

    print(f"No README found for {github_url}")
    return None  # or return ''

def main():
    """
    Main function that accepts a GitHub repository URL and prints the README content.
    """
    # Set up command-line argument parsing
    parser = argparse.ArgumentParser(description='Fetch and print the README content from a GitHub repository.')
    parser.add_argument('github_url', type=str, help='The GitHub repository URL')

    args = parser.parse_args()

    # Fetch README content and print it
    readme_content = get_readme_content(args.github_url)
    if readme_content is not None:
        print(readme_content)

if __name__ == '__main__':
    main()