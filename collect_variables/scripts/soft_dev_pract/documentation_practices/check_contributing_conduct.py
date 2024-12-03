"""
This script checks if GitHub repositories have `CONTRIBUTING.md` and 
`CODE_OF_CONDUCT.md` files. It processes repositories listed in a CSV 
file, checks the presence of these files in the root, `.github/`, and 
`docs/` directories. It uses the GitHub API and handles rate limiting 
by pausing execution for 20 minutes (or until rate limit resets) if 
the rate limit is reached. The results are saved to an output CSV file.

Required environment variables:
- GITHUB_TOKEN: GitHub Personal Access Token with appropriate permissions.

Usage:
    python script_name.py --input <input_file.csv> --output <output_file.csv>
"""

import os
import argparse
import pandas as pd
import time
from ghapi.all import GhApi
from dotenv import load_dotenv


def check_repository_files(api: GhApi, repo_owner: str, repo_name: str) -> bool:
    """
    Check if a repository contains `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` files.
    
    This function searches in the following directories:
    - Root directory
    - `.github/` folder
    - `docs/` folder
    
    Args:
        api (GhApi): Authenticated GitHub API client.
        repo_owner (str): The GitHub repository owner's username.
        repo_name (str): The GitHub repository name.
    
    Returns:
        bool: True if at least one of the files is found, otherwise False.
    """
    paths_to_check = [
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        ".github/CONTRIBUTING.md",
        ".github/CODE_OF_CONDUCT.md",
        "docs/CONTRIBUTING.md",
        "docs/CODE_OF_CONDUCT.md"
    ]
    for path in paths_to_check:
        try:
            api.repos.get_content(owner=repo_owner, repo=repo_name, path=path)
            return True  # File found
        except Exception:
            continue  # Ignore if file not found or error occurs
    return False


def check_rate_limit(api: GhApi) -> bool:
    """
    Check if the GitHub API rate limit has been reached. If the rate limit is 
    exceeded, the script sleeps until the rate limit resets.
    
    Args:
        api (GhApi): Authenticated GitHub API client.
    
    Returns:
        bool: True if the rate limit has been reached and the script is sleeping.
    """
    rate_limit = api.rate_limit.get()
    remaining = rate_limit.resources.core.remaining
    reset_time = rate_limit.resources.core.reset

    if remaining == 0:
        reset_timestamp = reset_time.timestamp()
        current_time = time.time()
        sleep_time = reset_timestamp - current_time + 60  # Adding 1 minute buffer
        print(f"Rate limit reached. Sleeping for {int(sleep_time // 60)} minutes...")
        time.sleep(sleep_time)
        return True
    return False


def process_repositories(input_csv: str, output_csv: str, token: str) -> None:
    """
    Processes each GitHub repository from the input CSV file, checks for the 
    presence of `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` files, and saves 
    the results in an output CSV file. The function handles rate limiting by 
    sleeping when the limit is exceeded.
    
    Args:
        input_csv (str): Path to the input CSV file containing repository URLs.
        output_csv (str): Path to the output CSV file where results will be saved.
        token (str): GitHub Personal Access Token for authentication.
    
    Returns:
        None
    """
    try:
        # Try reading the CSV with a semicolon delimiter
        df = pd.read_csv(input_csv, delimiter=';', encoding='utf-8')
    except UnicodeDecodeError:
        print(f"Error reading {input_csv} with UTF-8 encoding. Trying ISO-8859-1...")
        df = pd.read_csv(input_csv, delimiter=';', encoding='ISO-8859-1')

    # Check if 'html_url' column exists
    if 'html_url' not in df.columns:
        print(f"Error: The 'html_url' column is missing in the input CSV file.")
        return

    # Add columns for results
    df['has_contributing'] = None
    df['has_code_of_conduct'] = None

    api = GhApi(token=token)

    total_repos = len(df)
    completed = 0

    for index, row in df.iterrows():
        try:
            # Check rate limit before processing each repository
            if check_rate_limit(api):
                print(f"Rate limit reset, proceeding with next repository.")
            
            # Skip non-GitHub URLs
            if "github.com" not in row['html_url']:
                print(f"Skipping non-GitHub domain: {row['html_url']}")
                continue

            # Parse repository owner and name from URL
            parts = row['html_url'].replace("https://github.com/", "").split("/")
            if len(parts) < 2:
                continue
            repo_owner, repo_name = parts[0], parts[1]

            # Check for files
            df.at[index, 'has_contributing'] = check_repository_files(api, repo_owner, repo_name)
            df.at[index, 'has_code_of_conduct'] = check_repository_files(api, repo_owner, repo_name)
        except Exception as e:
            print(f"Skipping repository due to error: {row['html_url']} ({e})")
            continue
        finally:
            completed += 1
            print(f"Processed: {completed}/{total_repos}")

    # Save results to output CSV
    df.to_csv(output_csv, index=False)
    print(f"Results saved to {output_csv}")


def main() -> None:
    """
    Main function to parse command-line arguments and execute the script.
    
    Parses the input CSV file path, output CSV file path, and GitHub token 
    from the environment variables or command-line arguments. It then processes 
    the repositories and checks for the required files.
    
    Returns:
        None
    """
    # Get the directory of the current script
    script_dir = os.path.dirname(os.path.realpath(__file__))

    # Create the relative path to the .env file
    env_path = os.path.join(script_dir, '..', '..', '..', '..', '.env')

    # Load the .env file
    load_dotenv(dotenv_path=env_path, override=True)

    # Get the GITHUB_TOKEN from the .env file
    token = os.getenv('GITHUB_TOKEN')

    if not token:
        print("GitHub token not found in .env file.")
        return

    # Command-line argument parsing
    parser = argparse.ArgumentParser(description="Check for CONTRIBUTING.md and CODE_OF_CONDUCT.md in GitHub repositories.")
    parser.add_argument("--input", required=True, help="Path to the input CSV file.")
    parser.add_argument("--output", required=True, help="Path to the output CSV file.")
    args = parser.parse_args()

    # Process repositories
    process_repositories(args.input, args.output, token)


if __name__ == "__main__":
    main()
