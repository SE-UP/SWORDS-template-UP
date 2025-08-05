"""Checks GitHub repositories for the presence of a .pre-commit-config.yaml file and logs results to a CSV."""
import os
import argparse
import pandas as pd
from github import Github, GithubException, RateLimitExceededException
from dotenv import load_dotenv
import time

# Load .env file
script_dir = os.path.dirname(os.path.realpath(__file__))
env_path = os.path.join(script_dir, '..', '..', '..', '..', '.env')
load_dotenv(dotenv_path=env_path, override=True)

def check_ci_hook(html_url, github_instance):
    """
    Check if .pre-commit-config.yaml exists in the root of a GitHub repository.

    Args:
        html_url (str): The repository URL.
        github_instance (Github): Authenticated GitHub instance.

    Returns:
        str: 'Present', 'Not Present', or 'Error'.
    """
    try:
        # Extract owner and repo name from the URL
        if not html_url.startswith(('https://github.com', 'http://github.com')):
            return 'Not Supported'

        parts = html_url.rstrip('/').split('/')
        if len(parts) < 5:
            return 'Error'

        owner, repo_name = parts[-2], parts[-1]
        repo = github_instance.get_repo(f"{owner}/{repo_name}")

        # Check for the file in the root directory
        contents = repo.get_contents('/')
        for content in contents:
            if content.name == '.pre-commit-config.yaml':
                return 'Present'
        return 'Not Present'

    except RateLimitExceededException:
        print("Rate limit exceeded. Sleeping for 20 minutes...")
        time.sleep(20 * 60)  # Sleep for 20 minutes
        return check_ci_hook(html_url, github_instance)
    except GithubException as e:
        print(f"GitHub API error for {html_url}: {e}")
        return 'Error'
    except Exception as e:
        print(f"General error for {html_url}: {e}")
        return 'Error'

def main(input_csv, output_csv):
    # Get GitHub credentials from .env file
    token = os.getenv('GITHUB_TOKEN')
    username = os.getenv('GITHUB_USERNAME')

    if not token or not username:
        print("GitHub token or username not found in .env file.")
        return

    # Initialize GitHub instance
    github_instance = Github(token)

    # Read input CSV
    try:
        data = pd.read_csv(input_csv)
    except Exception as e:
        print(f"Error reading input file: {e}")
        return

    # Ensure html_url column exists
    if 'html_url' not in data.columns:
        print("Input file does not contain 'html_url' column.")
        return

    # Initialize result columns
    data['ci_hook'] = ''
    skipped_urls = []

    # Iterate over each URL
    for index, row in data.iterrows():
        html_url = row['html_url']
        print(f"Processing: {html_url}")

        try:
            result = check_ci_hook(html_url, github_instance)
            data.at[index, 'ci_hook'] = result

            if result in ['Error', 'Not Supported']:
                skipped_urls.append(html_url)

        except Exception as e:
            print(f"Error processing {html_url}: {e}")
            skipped_urls.append(html_url)

    # Save output
    try:
        data.to_csv(output_csv, index=False)
        print(f"Results saved to {output_csv}")

        # Save skipped URLs to a separate file
        skipped_file = output_csv.replace('.csv', '_skipped_urls.txt')
        with open(skipped_file, 'w') as f:
            for url in skipped_urls:
                f.write(f"{url}\n")
        print(f"Skipped URLs saved to {skipped_file}")

    except Exception as e:
        print(f"Error saving output file: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check for .pre-commit-config.yaml in GitHub repositories.")
    parser.add_argument("--input", required=True, help="Path to input CSV file.")
    parser.add_argument("--output", required=True, help="Path to output CSV file.")

    args = parser.parse_args()

    main(args.input, args.output)
