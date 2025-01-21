import os
import argparse
import requests
import pandas as pd
from dotenv import load_dotenv
import time

def load_credentials():
    """
    Load GITHUB_USERNAME and GITHUB_TOKEN from the .env file.
    """
    script_dir = os.path.dirname(os.path.realpath(__file__))
    env_path = os.path.join(script_dir, '..', '..', '..', '..', '.env')
    load_dotenv(dotenv_path=env_path, override=True)

    user = os.getenv('GITHUB_USERNAME')
    token = os.getenv('GITHUB_TOKEN')

    if not user or not token:
        raise ValueError("GITHUB_USERNAME or GITHUB_TOKEN not found. Please ensure the .env file is properly configured.")
    return user, token

def handle_rate_limit(response):
    """
    Handle GitHub API rate limiting. If the rate limit is reached, sleep for 20 minutes.
    """
    if response.status_code == 403 and "X-RateLimit-Remaining" in response.headers:
        remaining = int(response.headers["X-RateLimit-Remaining"])
        if remaining == 0:
            reset_time = int(response.headers.get("X-RateLimit-Reset", time.time() + 1200))
            wait_time = max(reset_time - time.time(), 0)
            print(f"Rate limit reached. Sleeping for {wait_time / 60:.2f} minutes...")
            time.sleep(wait_time + 1)  # Add an extra second to ensure reset
    elif response.status_code == 403:
        print("Rate limit reached but no reset header found. Sleeping for 20 minutes...")
        time.sleep(1200)  # Default to 20 minutes if reset time is unknown

def check_code_of_conduct_recursive(api_url, username, token):
    """
    Recursively check for code of conduct files in a repository's directory tree.
    """
    try:
        response = requests.get(api_url, auth=(username, token))
        if response.status_code == 403:
            handle_rate_limit(response)
            return check_code_of_conduct_recursive(api_url, username, token)

        response.raise_for_status()

        # If the response is not a list, return False (it means the API call didn't return directory contents)
        if not isinstance(response.json(), list):
            return False

        for item in response.json():
            # Check for files directly
            if item['type'] == 'file' and item['name'] in [
                'CODE_OF_CONDUCT.rst', 'CONDUCT.md', 'CONDUCT.rst']:
                return True

            # Recursively check subdirectories
            if item['type'] == 'dir':
                subdir_url = item['url']
                if check_code_of_conduct_recursive(subdir_url, username, token):
                    return True

        return False
    except requests.exceptions.RequestException as e:
        print(f"Error checking {api_url}: {e}")
        return False

def check_code_of_conduct_file(repo_url, username, token):
    """
    Check if the repository contains a code of conduct file in the root or subdirectories.
    """
    if not repo_url or not isinstance(repo_url, str) or "github.com" not in repo_url:
        print(f"Skipping non-GitHub or invalid repository URL: {repo_url}")
        return False

    try:
        # Extract the owner and repository name from the URL
        parts = repo_url.rstrip('/').split('/')
        owner, repo = parts[-2], parts[-1]

        # Print the repository being processed
        print(f"Processing repository: {owner}/{repo}")

        # GitHub API URL to list repository contents
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/"
        return check_code_of_conduct_recursive(api_url, username, token)

    except Exception as e:
        print(f"Error processing repository {repo_url}: {e}")
        return False

def process_csv(input_file, output_file, username, token):
    """
    Process the input CSV and write to the output CSV.
    """
    try:
        # Attempt to read CSV with UTF-8 encoding and ',' delimiter
        try:
            df = pd.read_csv(input_file, delimiter=',', encoding='utf-8')
        except UnicodeDecodeError:
            print(f"Error reading {input_file} with UTF-8 encoding. Trying ISO-8859-1...")
            df = pd.read_csv(input_file, delimiter=';', encoding='ISO-8859-1')

        # Add a new column for code of conduct file presence
        df['code_of_conduct_present'] = False
        for index, row in df.iterrows():
            repo_url = row.get('html_url', None)
            df.at[index, 'code_of_conduct_present'] = check_code_of_conduct_file(repo_url, username, token)

        # Write the updated DataFrame to the output file
        df.to_csv(output_file, index=False, encoding='utf-8')
        print(f"Output written to {output_file}")
    except Exception as e:
        print(f"Error processing CSV: {e}")

def main():
    parser = argparse.ArgumentParser(description="Check for code of conduct files in GitHub repositories.")
    parser.add_argument('input_csv', help="Path to the input CSV file")
    parser.add_argument('output_csv', help="Path to the output CSV file")
    args = parser.parse_args()

    # Load GitHub credentials
    username, token = load_credentials()

    # Process the CSV file
    process_csv(args.input_csv, args.output_csv, username, token)

if __name__ == "__main__":
    main()
