"""Checks GitHub repositories for CONTRIBUTING and CODE_OF_CONDUCT files and saves the results to a CSV."""
import os
import argparse
import pandas as pd
import time
from ghapi.all import GhApi
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed


def load_credentials():
    """
    Load GITHUB_USER and GITHUB_TOKEN from the .env file located relative to the script's directory.
    """
    # Get the directory of the current script
    script_dir = os.path.dirname(os.path.realpath(__file__))

    # Construct the relative path to the .env file
    env_path = os.path.join(script_dir, '..', '..', '..', '..', '.env')

    # Load the .env file
    load_dotenv(dotenv_path=env_path, override=True)

    # Get the GITHUB_USER and GITHUB_TOKEN from the .env file
    user = os.getenv('GITHUB_USER')
    token = os.getenv('GITHUB_TOKEN')

    if not user or not token:
        raise ValueError("GITHUB_USER or GITHUB_TOKEN not found. Please ensure the .env file is properly configured.")
    
    return user, token


def check_repository_files(api: GhApi, repo_owner: str, repo_name: str) -> bool:
    """
    Check if a repository contains `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` files.
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
    Check if the GitHub API rate limit has been reached. If exceeded, the script sleeps.
    """
    rate_limit = api.rate_limit.get()
    remaining = rate_limit.resources.core.remaining
    reset_time = rate_limit.resources.core.reset

    if remaining == 0:
        current_time = time.time()
        sleep_time = reset_time - current_time + 60  # Adding 1 minute buffer
        print(f"Rate limit reached. Sleeping for {int(sleep_time // 60)} minutes...")
        time.sleep(sleep_time)
        return True
    return False


def process_repository(api: GhApi, row):
    """
    Process a single repository: Check for files and return the result.
    """
    html_url = row.get('html_url')
    if not html_url or "github.com" not in html_url:
        return None, None  # Skip non-GitHub URLs

    try:
        # Parse repository owner and name
        parts = html_url.replace("https://github.com/", "").split("/")
        if len(parts) < 2:
            return None, None  # Invalid repository URL
        repo_owner, repo_name = parts[0], parts[1]

        # Check for files
        has_contributing = check_repository_files(api, repo_owner, repo_name)
        has_code_of_conduct = check_repository_files(api, repo_owner, repo_name)
        return has_contributing, has_code_of_conduct
    except Exception as e:
        print(f"Error processing repository: {html_url} ({e})")
        return None, None


def process_repositories(input_csv: str, output_csv: str, user: str, token: str, batch_size: int = 10, max_threads: int = 5) -> None:
    """
    Processes repositories in batches with partial saving and parallel processing.
    """
    try:
        df = pd.read_csv(input_csv, delimiter=';', encoding='utf-8')
    except UnicodeDecodeError:
        print(f"Error reading {input_csv} with UTF-8 encoding. Trying ISO-8859-1...")
        df = pd.read_csv(input_csv, delimiter=';', encoding='ISO-8859-1')

    # Check if 'html_url' column exists
    if 'html_url' not in df.columns:
        print(f"Error: The 'html_url' column is missing in the input CSV file.")
        return

    # Add result columns if not present
    if 'has_contributing' not in df.columns:
        df['has_contributing'] = None
    if 'has_code_of_conduct' not in df.columns:
        df['has_code_of_conduct'] = None

    api = GhApi(owner=user, token=token)
    total_repos = len(df)

    with ThreadPoolExecutor(max_threads) as executor:
        futures = {}
        for index, row in df.iterrows():
            # Check rate limit before submitting tasks
            if check_rate_limit(api):
                print("Rate limit reset. Continuing...")

            # Skip if already processed
            if pd.notnull(df.at[index, 'has_contributing']) and pd.notnull(df.at[index, 'has_code_of_conduct']):
                continue

            # Log repository being processed
            print(f"Processing repository: {row['html_url']} (Index: {index})")

            futures[executor.submit(process_repository, api, row)] = index

        completed = 0
        for future in as_completed(futures):
            index = futures[future]
            try:
                has_contributing, has_code_of_conduct = future.result()
                df.at[index, 'has_contributing'] = has_contributing
                df.at[index, 'has_code_of_conduct'] = has_code_of_conduct
            except Exception as e:
                print(f"Error processing index {index}: {e}")
            finally:
                completed += 1
                print(f"Processed: {completed}/{total_repos}")

                # Save partial results every batch_size
                if completed % batch_size == 0:
                    df.to_csv(output_csv, index=False)
                    print(f"Partial results saved at {completed}/{total_repos}")

    # Final save
    df.to_csv(output_csv, index=False)
    print(f"Final results saved to {output_csv}")


def main() -> None:
    """
    Main function to parse command-line arguments and execute the script.
    """
    # Load the GitHub user and token
    user, token = load_credentials()

    # Command-line argument parsing
    parser = argparse.ArgumentParser(description="Check for CONTRIBUTING.md and CODE_OF_CONDUCT.md in GitHub repositories.")
    parser.add_argument("--input", required=True, help="Path to the input CSV file.")
    parser.add_argument("--output", required=True, help="Path to the output CSV file.")
    args = parser.parse_args()

    # Process repositories
    process_repositories(args.input, args.output, user, token)


if __name__ == "__main__":
    main()
