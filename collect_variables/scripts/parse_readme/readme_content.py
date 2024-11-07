"""
Processes a CSV file containing GitHub repository URLs, retrieves README content from each repository,
and appends this content to a new CSV file. Uses GitHub's API to access README files and manages API
rate limits by retrying requests after a delay if limits are exceeded. Requires a GitHub token in a
.env file for API authentication. Special characters removed from README content include commas, 
line breaks, semicolons, and carriage returns to ensure single-cell entries in the output CSV file.
"""

import os
import logging
import time
import argparse
from csv import QUOTE_MINIMAL
import pandas as pd
from requests import get
from requests.exceptions import HTTPError
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Internal delimiter for reading CSV
CSV_DELIMITER = ';'  # Adjust this to the delimiter used in the input CSV file

def is_github_url(url):
    """
    Checks if a URL is a GitHub repository URL.
    
    Args:
        url (str): The URL string to check.

    Returns:
        bool: True if the URL is a valid GitHub repository URL, False otherwise.
    """
    return isinstance(url, str) and url.startswith('https://github.com/')

def get_owner_repo_from_url(url):
    """
    Extracts the owner and repository name from a GitHub repository URL.
    
    Args:
        url (str): The GitHub repository URL.

    Returns:
        tuple: A tuple containing the repository owner (str) and repository name (str), or (None, None) if the URL is invalid.
    """
    if not is_github_url(url):
        return None, None
    parts = url.strip().split('/')
    if len(parts) >= 5:
        owner = parts[3]
        repo = parts[4].replace('.git', '')
        return owner, repo
    return None, None

def fetch_readme_content(owner, repo, token):
    """
    Fetches the README file content from the root directory of a GitHub repository.
    
    Args:
        owner (str): The repository owner's GitHub username.
        repo (str): The repository name.
        token (str): GitHub API token for authentication.

    Returns:
        str: The content of the README file, or an empty string if fetching fails.
    """
    headers = {'Authorization': f'token {token}'}
    try:
        response = get(f'https://api.github.com/repos/{owner}/{repo}/contents', headers=headers)
        response.raise_for_status()
        contents = response.json()
        for content in contents:
            if content['type'] == 'file' and content['name'].lower() in ['readme.md', 'readme', 'readme.rst']:
                readme_response = get(content['download_url'])
                readme_response.raise_for_status()
                return readme_response.text
    except HTTPError as http_err:
        if http_err.response.status_code == 403 and 'X-RateLimit-Remaining' in http_err.response.headers and \
           http_err.response.headers['X-RateLimit-Remaining'] == '0':
            logging.warning("Rate limit exceeded. Sleeping for 20 minutes.")
            time.sleep(1200)
            return fetch_readme_content(owner, repo, token)
        logging.error("HTTP error occurred: %s", http_err)
    except Exception as err:
        logging.error("An error occurred: %s", err)
    return ""

def process_csv(input_csv, output_csv):
    """
    Processes the CSV file to fetch README content from GitHub repositories and update the CSV with the README content.
    
    Args:
        input_csv (str): Path to the input CSV file containing a column 'html_url' with GitHub repository URLs.
        output_csv (str): Path to save the updated CSV file with an added 'readme' column.

    Returns:
        None
    """
    df = pd.read_csv(input_csv, delimiter=CSV_DELIMITER, encoding='ISO-8859-1')

    if 'html_url' not in df.columns:
        logging.error("Input CSV must contain 'html_url' column.")
        return

    script_dir = os.path.dirname(os.path.realpath(__file__))
    env_path = os.path.join(script_dir, '..', '..', '..', '.env')
    load_dotenv(dotenv_path=env_path, override=True)
    token = os.getenv('GITHUB_TOKEN')
    if not token:
        logging.error("GitHub token not found in .env file.")
        return

    readme_contents = []
    for url in df['html_url']:
        if pd.isna(url):
            logging.warning("Skipping NaN value in 'html_url' column.")
            readme_contents.append('')
            continue

        url = str(url).strip()

        if not is_github_url(url):
            logging.warning("Skipping non-GitHub URL: %s", url)
            readme_contents.append('')
            continue

        owner, repo = get_owner_repo_from_url(url)
        if not owner or not repo:
            logging.warning("Skipping invalid GitHub URL: %s", url)
            readme_contents.append('')
            continue

        logging.info("Processing URL: %s", url)
        try:
            readme_content = fetch_readme_content(owner, repo, token)
            readme_contents.append(readme_content)
        except Exception as fetch_err:
            logging.error("Failed to fetch README for %s: %s", url, fetch_err)
            readme_contents.append('')

    df['readme'] = readme_contents

    df['readme'] = df['readme'].str.replace('[,\r\n;]', ' ', regex=True)
    df.to_csv(output_csv, index=False, quotechar='"', quoting=QUOTE_MINIMAL, encoding='utf-8')
    logging.info("Processing complete. Updated CSV saved to %s", output_csv)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch README content from GitHub repositories listed in a CSV file.")
    parser.add_argument('--input', required=True, help="Path to the input CSV file")
    parser.add_argument('--output', required=True, help="Path to the output CSV file")

    args = parser.parse_args()

    process_csv(args.input, args.output)
