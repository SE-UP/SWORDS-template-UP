"""
Checks GitHub repositories for CONTRIBUTING and CODE_OF_CONDUCT files
and saves the results to a CSV.

Usage:
    python script.py --input input.csv --output output.csv
"""
import os
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from ghapi.all import GhApi
from dotenv import load_dotenv



def load_credentials():
    """
    Load GITHUB_USER and GITHUB_TOKEN from the .env file located relative to the script's directory.

    Returns:
        tuple: (user, token) strings.
    """
    script_dir = os.path.dirname(os.path.realpath(__file__))
    env_path = os.path.join(script_dir, '..', '..', '..', '..', '.env')
    load_dotenv(dotenv_path=env_path, override=True)
    user = os.getenv("GITHUB_USER")
    token = os.getenv("GITHUB_TOKEN")
    if not user or not token:
        raise ValueError("GITHUB_USER or GITHUB_TOKEN not found. "
                         "Please ensure the .env file is properly configured.")
    return user, token


def check_repository_files(api: GhApi, repo_owner: str, repo_name: str, target_file: str) -> bool:
    """
    Check if a repository contains a specific file.
    Args:
        api (GhApi): Authenticated GhApi instance.
        repo_owner (str): Repository owner.
        repo_name (str): Repository name.
        target_file (str): File path to check.

    Returns:
        bool: True if file exists, False otherwise.
    """
    try:
        api.repos.get_content(owner=repo_owner, repo=repo_name, path=target_file)
        return True
    except Exception:
        return False


def check_rate_limit(api: GhApi) -> bool:
    """
    Check if the GitHub API rate limit has been reached. If exceeded, sleeps until reset.
    Args:
        api (GhApi): Authenticated GhApi instance.

    Returns:
        bool: True if slept due to rate limiting, False otherwise.
    """
    rate_limit = api.rate_limit.get()
    remaining = rate_limit.resources.core.remaining
    reset_time = rate_limit.resources.core.reset

    if remaining == 0:
        current_time = time.time()
        sleep_time = reset_time - current_time + 60  # Add a buffer
        print(f"Rate limit reached. Sleeping for {int(sleep_time // 60)} minutes...")
        time.sleep(sleep_time)
        return True
    return False


def process_repository(api: GhApi, row):
    """
    Process a single repository: Check for CONTRIBUTING and CODE_OF_CONDUCT files.

    Args:
        api (GhApi): Authenticated GhApi instance.
        row (pd.Series): DataFrame row with 'html_url'.

    Returns:
        tuple: (has_contributing: bool, has_code_of_conduct: bool)
    """
    html_url = row.get("html_url")
    if not html_url or "github.com" not in html_url:
        return None, None

    try:
        parts = html_url.replace("https://github.com/", "").split("/")
        if len(parts) < 2:
            return None, None
        repo_owner, repo_name = parts[0], parts[1]

        contributing_paths = [
            "CONTRIBUTING.md",
            ".github/CONTRIBUTING.md",
            "docs/CONTRIBUTING.md"
        ]
        code_of_conduct_paths = [
            "CODE_OF_CONDUCT.md",
            ".github/CODE_OF_CONDUCT.md",
            "docs/CODE_OF_CONDUCT.md"
        ]

        has_contributing = any(
            check_repository_files(api, repo_owner, repo_name, path)
            for path in contributing_paths
        )
        has_code_of_conduct = any(
            check_repository_files(api, repo_owner, repo_name, path)
            for path in code_of_conduct_paths
        )
        return has_contributing, has_code_of_conduct
    except Exception as exc:
        print(f"Error processing repository: {html_url} ({exc})")
        return None, None


def process_repositories(
    input_csv: str,
    output_csv: str,
    user: str,
    token: str,
    batch_size: int = 10,
    max_threads: int = 5,
) -> None:
    """
    Processes repositories with partial saving and parallel processing.

    Args:
        input_csv (str): Path to input CSV.
        output_csv (str): Output CSV path.
        user (str): GitHub user.
        token (str): GitHub token.
        batch_size (int): Batch size for partial saving.
        max_threads (int): Max number of threads to use.
    """
    try:
        df = pd.read_csv(input_csv, delimiter=";", encoding="utf-8")
    except UnicodeDecodeError:
        print(
            f"Error reading {input_csv} with UTF-8 encoding. "
            "Trying ISO-8859-1..."
        )
        df = pd.read_csv(input_csv, delimiter=";", encoding="ISO-8859-1")

    if "html_url" not in df.columns:
        print("Error: The 'html_url' column is missing in the input CSV file.")
        return

    if "has_contributing" not in df.columns:
        df["has_contributing"] = None
    if "has_code_of_conduct" not in df.columns:
        df["has_code_of_conduct"] = None

    api = GhApi(owner=user, token=token)
    total_repos = len(df)
    completed = 0

    with ThreadPoolExecutor(max_threads) as executor:
        futures = {}
        for index, row in df.iterrows():
            if check_rate_limit(api):
                print("Rate limit reset. Continuing...")

            if (
                    pd.notnull(df.at[index, "has_contributing"])
                    and pd.notnull(df.at[index, "has_code_of_conduct"])
            ):
                continue

            print(f"Processing repository: {row['html_url']} (Index: {index})")
            futures[executor.submit(process_repository, api, row)] = index

        for future in as_completed(futures):
            index = futures[future]
            try:
                has_contributing, has_code_of_conduct = future.result()
                df.at[index, "has_contributing"] = has_contributing
                df.at[index, "has_code_of_conduct"] = has_code_of_conduct
            except Exception as exc:
                print(f"Error processing index {index}: {exc}")
            finally:
                completed += 1
                print(f"Processed: {completed}/{total_repos}")

                if completed % batch_size == 0:
                    df.to_csv(output_csv, index=False)
                    print(f"Partial results saved at {completed}/{total_repos}")

    df.to_csv(output_csv, index=False)
    print(f"Final results saved to {output_csv}")


def main():
    """
    Main function to parse command-line arguments and execute the script.
    """
    user, token = load_credentials()
    parser = argparse.ArgumentParser(
        description="Check for CONTRIBUTING.md and CODE_OF_CONDUCT.md in GitHub repositories."
    )
    parser.add_argument("--input", required=True, help="Path to the input CSV file.")
    parser.add_argument("--output", required=True, help="Path to the output CSV file.")
    args = parser.parse_args()
    process_repositories(args.input, args.output, user, token)


if __name__ == "__main__":
    main()
