import os
import pandas as pd
import logging
import time
from requests import get
from requests.exceptions import HTTPError
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Internal delimiter for reading CSV
CSV_DELIMITER = ','  # Change this to the delimiter used in your CSV file

def is_github_url(url):
    """
    Check if a URL is a GitHub repository URL.
    """
    return url.startswith('https://github.com/')

def get_owner_repo_from_url(url):
    """
    Extract the owner and repository name from a GitHub repository URL.
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
    Fetch the README file content from the root directory of a GitHub repository.
    """
    headers = {'Authorization': f'token {token}'}
    try:
        # Fetch repository contents
        response = get(f'https://api.github.com/repos/{owner}/{repo}/contents', headers=headers)
        response.raise_for_status()
        contents = response.json()
        
        # Find README file
        for content in contents:
            if content['type'] == 'file' and content['name'].lower() in ['readme.md', 'readme', 'readme.rst']:
                readme_response = get(content['download_url'])
                readme_response.raise_for_status()
                return readme_response.text

    except HTTPError as e:
        if e.response.status_code == 403 and 'X-RateLimit-Remaining' in e.response.headers and e.response.headers['X-RateLimit-Remaining'] == '0':
            logging.warning("Rate limit exceeded. Sleeping for 20 minutes.")
            time.sleep(1200)  # Sleep for 20 minutes
            return fetch_readme_content(owner, repo, token)  # Retry the same URL
        logging.error(f"HTTP error: {e}")
    except Exception as e:
        logging.error(f"Error: {e}")
    
    return ""

def process_csv(input_csv, output_csv):
    """
    Process the CSV file to fetch the README content from repositories and update the CSV.
    """
    df = pd.read_csv(input_csv, delimiter=';')
    if 'html_url' not in df.columns:
        logging.error("Input CSV must contain 'html_url' column.")
        return

    # Load GitHub token from .env file
    script_dir = os.path.dirname(os.path.realpath(__file__))
    env_path = os.path.join(script_dir, '..', '..', '..', '.env')
    load_dotenv(dotenv_path=env_path, override=True)
    token = os.getenv('GITHUB_TOKEN')
    
    if not token:
        logging.error("GitHub token not found in .env file.")
        return

    readme_contents = []
    
    for url in df['html_url']:
        if not is_github_url(url):
            logging.warning(f"Skipping non-GitHub URL: {url}")
            readme_contents.append('')
            continue

        owner, repo = get_owner_repo_from_url(url)
        if not owner or not repo:
            logging.warning(f"Skipping invalid GitHub URL: {url}")
            readme_contents.append('')
            continue

        logging.info(f"Processing URL: {url}")
        readme_content = fetch_readme_content(owner, repo, token)
        readme_contents.append(readme_content)
    
    df['readme'] = readme_contents

    # Clean the README content
    df['readme'] = df['readme'].str.replace('\n', ' ').str.replace(';', '').str.replace(',', '')

    df.to_csv(output_csv, index=False)
    logging.info(f"Processing complete. Updated CSV saved to {output_csv}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch README content from GitHub repositories listed in a CSV file.")
    parser.add_argument('--input', required=True, help="Path to the input CSV file")
    parser.add_argument('--output', required=True, help="Path to the output CSV file")

    args = parser.parse_args()

    process_csv(args.input, args.output)
