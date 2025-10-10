"""
Checks 'test' or 'tests' directories at the root level of GitHub
repositories specified in a CSV file.
"""

import os
import time
import argparse
from typing import Optional, Set

import pandas as pd
from github import Github, GithubException, RateLimitExceededException  # pylint: disable=E0611
from dotenv import load_dotenv
from urllib.parse import urlparse

# Get the directory of the current script
script_dir = os.path.dirname(os.path.realpath(__file__))

# Create the relative path to the .env file
env_path = os.path.join(script_dir, '..', '..', '..','..', '.env')

# Load the .env file
load_dotenv(dotenv_path=env_path, override=True)

# Get the GITHUB_TOKEN and GITHUB_USERNAME from the .env file
token = os.getenv('GITHUB_TOKEN')
username = os.getenv('GITHUB_USERNAME')

# Use the token to create a Github instance
github_instance = Github(token)


def _normalize_owner_repo(html_url: str) -> Optional[str]:
    """
    Normalize and parse a URL into "owner/repo" for GitHub.

    Accepts:
      - http(s)://github.com/owner/repo
      - http(s)://www.github.com/owner/repo
      - github.com/owner/repo
      - www.github.com/owner/repo

    Returns "owner/repo" on success; None for non-GitHub/malformed URLs.
    """
    if html_url is None:
        return None

    url = str(html_url).strip()
    if not url:
        return None

    # Add scheme for bare domains
    if url.startswith("github.com/") or url.startswith("www.github.com/"):
        url = "https://" + url

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in {"github.com", "www.github.com"}:
        return None

    parts = [p for p in (parsed.path or "").split("/") if p]
    if len(parts) < 2:
        return None

    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]

    return f"{owner}/{repo}"


def check_test_folder(repo) -> bool:
    """
    Check if a GitHub repository has a 'test' or
    'tests' folder in its root directory.

    Parameters:
    repo (github.Repository.Repository): The GitHub repository to check.

    Returns:
    bool: True if 'test' or 'tests' (or 'inst') folder is found, False otherwise.
    """
    try:
        contents = repo.get_contents("")
        for content in contents:
            if content.type == "dir" and content.name.lower() in ["test", "tests", "inst"]:
                return True
        return False
    except GithubException as github_exception:
        print(f"Error accessing repository: {github_exception}")
        # The caller decides how to record errors (we'll set NA in main)
        return False


def handle_rate_limit_error(exc: GithubException) -> None:
    """
    Sleep 20 minutes when API rate limit is exceeded.
    """
    msg = ""
    try:
        msg = exc.data.get("message", "")
    except Exception:
        pass
    if "API rate limit exceeded" in msg:
        print("Rate limit exceeded. Sleeping for 20 minutes...")
        time.sleep(20 * 60)


def _read_input_csv(path: str) -> Optional[pd.DataFrame]:
    try:
        # Keep original behavior: semicolon input is common in your datasets
        return pd.read_csv(path, sep=';', encoding='ISO-8859-1', on_bad_lines='warn')
    except Exception as exc:
        print(f"Error reading input CSV {path}: {exc}")
        return None


def _load_existing_output(path: str) -> Optional[pd.DataFrame]:
    if not os.path.exists(path):
        return None
    try:
        # Output is standard CSV (comma-separated)
        return pd.read_csv(path)
    except Exception as exc:
        print(f"Error reading existing output CSV {path}: {exc}")
        return None


def _outer_union_on_html_url(old_df: Optional[pd.DataFrame], new_df: pd.DataFrame) -> pd.DataFrame:
    """
    Outer-union old and new by 'html_url' without losing columns/records.
    Prefer existing values; fill gaps from new.
    """
    if old_df is None:
        return new_df.copy()

    if "html_url" not in old_df.columns or "html_url" not in new_df.columns:
        return new_df.copy()

    old_idx = old_df.set_index("html_url")
    new_idx = new_df.set_index("html_url")
    combined = old_idx.combine_first(new_idx)

    # Bring in any columns only present in the new df
    for col in new_idx.columns.difference(combined.columns):
        combined[col] = new_idx[col]

    return combined.reset_index()


def main(input_csv: str, output_csv: str) -> None:
    """
    Main function to read the CSV file, check the repositories,
    and update the CSV file.

    Parameters:
    input_csv (str): The path to the input CSV file.
    output_csv (str): The path to the output CSV file.
    """
    input_df = _read_input_csv(input_csv)
    if input_df is None:
        return

    if 'html_url' not in input_df.columns:
        print("Input CSV must contain 'html_url' column.")
        return

    # Load existing output (if any) and outer-merge so nothing is lost
    existing_df = _load_existing_output(output_csv)
    merged_df = _outer_union_on_html_url(existing_df, input_df)

    # Ensure target column exists with proper nullable boolean dtype
    if 'test_folder' not in merged_df.columns:
        merged_df['test_folder'] = pd.Series([pd.NA] * len(merged_df), dtype="boolean")
    else:
        merged_df['test_folder'] = merged_df['test_folder'].astype("boolean")

    # Only (re)process URLs from the current input
    to_process: Set[str] = set(map(str, input_df['html_url'].tolist()))

    processed = 0
    for idx, row in merged_df.iterrows():
        url = row['html_url']

        # Only process current input rows; preserve others
        if str(url) not in to_process:
            continue

        # Skip null/empty URLs but keep the row as NA
        if pd.isna(url) or not str(url).strip():
            print(f"Skipping row with missing URL at index {idx}")
            merged_df.at[idx, 'test_folder'] = pd.NA
            continue

        owner_repo = _normalize_owner_repo(str(url))
        if owner_repo is None:
            print(f"Skipping non-GitHub or malformed URL: {url}")
            merged_df.at[idx, 'test_folder'] = pd.NA  # NA for non-GitHub domains
            continue

        print(f"Working on repository: {url}")
        try:
            repo = github_instance.get_repo(owner_repo)
            has_tests = check_test_folder(repo)
            merged_df.at[idx, 'test_folder'] = bool(has_tests)
            processed += 1
            print(f"Repositories completed: {processed}")

            # Persist progress after each repository
            merged_df.to_csv(output_csv, index=False)

        except RateLimitExceededException as exc:
            handle_rate_limit_error(exc)
            # mark as NA and continue
            merged_df.at[idx, 'test_folder'] = pd.NA
            merged_df.to_csv(output_csv, index=False)
            continue
        except GithubException as exc:
            handle_rate_limit_error(exc)
            print(f"Error accessing repository {owner_repo}: {exc}")
            merged_df.at[idx, 'test_folder'] = pd.NA
            merged_df.to_csv(output_csv, index=False)
            continue

    # Final save
    merged_df.to_csv(output_csv, index=False)


if __name__ == "__main__":
    DESCRIPTION = 'Check for test folders in GitHub repositories.'
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument('--input', type=str,
                        default='../collect_repositories/results/repositories_filtered.csv',
                        help='Input CSV file')
    parser.add_argument('--output', type=str, default='results/soft_dev_pract.csv',
                        help='Output CSV file')
    args = parser.parse_args()
    main(args.input, args.output)
