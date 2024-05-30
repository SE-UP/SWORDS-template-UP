"""
This script checks for the presence of folders .github (github actions) in the root
directory of GitHub repositories listed in a CSV file. It uses the GitHub API
to access the repositories and updates the CSV file with the results.
"""

import argparse
import os
import pandas as pd
import time
from github import Github, GithubException, RateLimitExceededException
from dotenv import load_dotenv

# Get the directory of the current script
script_dir = os.path.dirname(os.path.realpath(__file__))

# Create the relative path to the .env file
env_path = os.path.join(script_dir, '..', '..', '..', '.env')

# Load the .env file
load_dotenv(dotenv_path=env_path, override=True)

# Get the GITHUB_TOKEN and GITHUB_USERNAME from the .env file
token = os.getenv('GITHUB_TOKEN')
username = os.getenv('GITHUB_USERNAME')
print(f"Token: {token}")
print(f"Username: {username}")

# Use the token to create a Github instance
g = Github(token)

def check_github_actions(repo):
    """
    Check if a GitHub repository has implemented GitHub Actions.

    Parameters:
    repo (github.Repository.Repository): The GitHub repository to check.

    Returns:
    bool: True if '.github/workflows' directory is found, False otherwise.
    """
    try:
        contents = repo.get_contents("")
        for content in contents:
            if content.type == "dir" and content.name == ".github":
                github_contents = repo.get_contents(content.path)
                for github_content in github_contents:
                    if github_content.type == "dir" and github_content.name == "workflows":
                        return True
        return False
    except GithubException as e:
        print(f"Error accessing repository: {e}")
        return False


def main(csv_file):
    """
    Main function to read the CSV file, check the repositories,
      and update the CSV file.

    Parameters:
    csv_file (str): The path to the CSV file.
    """
    df = pd.read_csv(csv_file, sep=',', on_bad_lines='warn') # cheange sep to ',' from ';' when using the csv file
    if 'github_actions' not in df.columns:
        df['github_actions'] = None

    count = 0
    for index, row in df.iterrows():
        url = row['html_url']
        if pd.isna(url):
            print("Skipping row with missing URL")
            continue
        if not pd.isna(row['github_actions']):
            print(f"Skipping repository {url} with existing GitHub Actions value: {row['github_actions']}")
            continue
        print(f"Working on repository: {url}")
        repo_name = url.split('https://github.com/')[-1]
        try:
            repo = g.get_repo(repo_name)
            df.loc[index, 'github_actions'] = check_github_actions(repo)
            count += 1
            print(f"Repositories completed: {count}")
            df.to_csv(csv_file, index=False)  # Save to CSV after each repository is checked
        except RateLimitExceededException as e:
            print("Rate limit exceeded. Sleeping until reset...")
            reset_time = g.rate_limiting_resettime
            sleep_time = reset_time - int(time.time())
            if sleep_time > 0:
                time.sleep(sleep_time)
            continue
        except GithubException as e:
            print(f"Error accessing repository {repo_name}: {e}")
            continue

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Check for GitHub Actions in GitHub repositories.')
    parser.add_argument('csv_file', type=str, help='Input CSV file')
    args = parser.parse_args()
    main(args.csv_file)