"""
This script checks for the presence of folders .github (GitHub Actions)
in the root directory of GitHub repositories listed in a CSV file.
It uses the GitHub API to access the repositories and updates the CSV file with the results.
"""

import argparse
import os
import time
from typing import Optional, Tuple, List, Set

import pandas as pd
from github import Github, GithubException  # pylint: disable=E0611
from dotenv import load_dotenv
from urllib.parse import urlparse

# Get the directory of the current script
script_dir = os.path.dirname(os.path.realpath(__file__))

# Create the relative path to the .env file
env_path = os.path.join(script_dir, '..', '..', '..','..', '.env')

# Load the .env file
load_dotenv(dotenv_path=env_path, override=True)

# Get the GITHUB_TOKEN from the .env file
token = os.getenv('GITHUB_TOKEN')

# Use the token to create a Github instance
g = Github(token)


def _parse_github_owner_repo(html_url: str) -> Optional[str]:
    """
    Normalize and parse a URL into the "owner/repo" string for GitHub.

    Accepts:
      - http(s)://github.com/owner/repo
      - http(s)://www.github.com/owner/repo
      - github.com/owner/repo
      - www.github.com/owner/repo

    Returns "owner/repo" on success, or None for non-GitHub/malformed URLs.
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


def check_github_actions(repo):
    """
    Check if a GitHub repository has implemented GitHub Actions.

    Parameters:
    repo (github.Repository.Repository): The GitHub repository to check.

    Returns:
    str: 'github_actions' if '.github/workflows' directory is found, None otherwise.
    """
    try:
        contents = repo.get_contents("")
        for content in contents:
            if content.type == "dir" and content.name == ".github":
                github_contents = repo.get_contents(content.path)
                for github_content in github_contents:
                    if (github_content.type == "dir" and
                            github_content.name == "workflows"):
                        return 'github_actions'
        return None
    except GithubException as github_exception:
        print(f"Error accessing repository: {github_exception}")
        return None


def check_travis(repo):
    """
    Check if a GitHub repository has implemented Travis CI.

    Parameters:
    repo (github.Repository.Repository): The GitHub repository to check.

    Returns:
    str: 'travis' if '.travis.yml' file is found, None otherwise.
    """
    try:
        repo.get_contents(".travis.yml")
        return 'travis'
    except GithubException as github_exception:
        print(f"Error accessing repository: {github_exception}")
        return None


def check_circleci(repo):
    """
    Check if a GitHub repository has implemented CircleCI.

    Parameters:
    repo (github.Repository.Repository): The GitHub repository to check.

    Returns:
    str: 'circleci' if '.circleci/config.yml' file is found, None otherwise.
    """
    try:
        repo.get_contents(".circleci/config.yml")
        return 'circleci'
    except GithubException as github_exception:
        print(f"Error accessing repository: {github_exception}")
        return None


def check_jenkins(repo):
    """
    Check if a GitHub repository has implemented Jenkins.

    Parameters:
    repo (github.Repository.Repository): The GitHub repository to check.

    Returns:
    str: 'jenkins' if 'Jenkinsfile' is found, None otherwise.
    """
    try:
        repo.get_contents("Jenkinsfile")
        return 'jenkins'
    except GithubException as github_exception:
        print(f"Error accessing repository: {github_exception}")
        return None


def check_azure_pipelines(repo):
    """
    Check if a GitHub repository has implemented Azure Pipelines.

    Parameters:
    repo (github.Repository.Repository): The GitHub repository to check.

    Returns:
    str: 'azure_pipelines' if 'azure-pipelines.yml' file is found, None otherwise.
    """
    try:
        repo.get_contents("azure-pipelines.yml")
        return 'azure_pipelines'
    except GithubException as github_exception:
        print(f"Error accessing repository: {github_exception}")
        return None


def handle_rate_limit_error(exception):
    """
    Handle GitHub API rate limit exceeded error by sleeping for 20 minutes.

    Parameters:
    exception (GithubException): The exception object that contains the error details.
    """
    error_message = exception.data.get("message", "")
    if "API rate limit exceeded" in error_message:
        print("Rate limit exceeded. Sleeping for 20 minutes...")
        time.sleep(20 * 60)  # Sleep for 20 minutes


def _read_input_csv(path: str) -> Optional[pd.DataFrame]:
    try:
        # Keep your original semicolon input for compatibility
        return pd.read_csv(path, sep=';', on_bad_lines='warn')
    except Exception as exc:
        print(f"Error reading input CSV {path}: {exc}")
        return None


def _load_existing_output(path: str) -> Optional[pd.DataFrame]:
    if not os.path.exists(path):
        return None
    try:
        # Assume standard comma-separated output
        return pd.read_csv(path)
    except Exception as exc:
        print(f"Error reading existing output CSV {path}: {exc}")
        return None


def _outer_union_on_html_url(old_df: Optional[pd.DataFrame], new_df: pd.DataFrame) -> pd.DataFrame:
    """
    Outer-union old and new by 'html_url' without losing columns/records.
    Prefer existing values where both have data; fill gaps from new.
    """
    if old_df is None:
        return new_df.copy()

    if "html_url" not in old_df.columns or "html_url" not in new_df.columns:
        return new_df.copy()

    old_idx = old_df.set_index("html_url")
    new_idx = new_df.set_index("html_url")
    combined = old_idx.combine_first(new_idx)

    # Bring in any columns present only in the new df
    for col in new_idx.columns.difference(combined.columns):
        combined[col] = new_idx[col]

    return combined.reset_index()


def main(input_csv_file, output_csv_file):
    """
    Main function to check for continuous integration tools in GitHub repositories.

    Parameters:
    input_csv_file (str): Path to the input CSV file.
    output_csv_file (str): Path to the output CSV file.
    """
    input_df = _read_input_csv(input_csv_file)
    if input_df is None:
        return

    if 'html_url' not in input_df.columns:
        print("Input CSV must contain 'html_url' column.")
        return

    # Load existing output (if any) and outer-merge so nothing is lost
    existing_df = _load_existing_output(output_csv_file)
    merged_df = _outer_union_on_html_url(existing_df, input_df)

    # Ensure target columns exist with correct dtypes
    if 'continuous_integration' not in merged_df.columns:
        merged_df['continuous_integration'] = pd.Series([pd.NA] * len(merged_df), dtype="boolean")
    else:
        merged_df['continuous_integration'] = merged_df['continuous_integration'].astype("boolean")

    if 'ci_tool' not in merged_df.columns:
        merged_df['ci_tool'] = pd.Series([pd.NA] * len(merged_df), dtype="string")
    else:
        merged_df['ci_tool'] = merged_df['ci_tool'].astype("string")

    # Only (re)process the URLs from the current input
    to_process: Set[str] = set(map(str, input_df['html_url'].tolist()))

    ci_checks = [
        check_github_actions,
        check_travis,
        check_circleci,
        check_jenkins,
        check_azure_pipelines
    ]

    processed_count = 0
    for index, row in merged_df.iterrows():
        url = row['html_url']

        # Process only current input rows
        if str(url) not in to_process:
            continue

        # Skip empty/null URLs, but keep the row
        if pd.isna(url) or not str(url).strip():
            print(f"Skipping row with missing or null URL at index {index}")
            merged_df.at[index, 'continuous_integration'] = pd.NA
            merged_df.at[index, 'ci_tool'] = pd.NA
            continue

        # Accept http/https/www/bare github.com — normalize and validate
        owner_repo = _parse_github_owner_repo(str(url))
        if owner_repo is None:
            print(f"Skipping non-GitHub or malformed URL: {url}")
            merged_df.at[index, 'continuous_integration'] = pd.NA  # non-GitHub domain -> NA
            merged_df.at[index, 'ci_tool'] = pd.NA
            continue

        print(f"Working on repository: {url}")
        try:
            repo = g.get_repo(owner_repo)
            ci_found: Optional[str] = None
            for ci_check in ci_checks:
                ci_tool = ci_check(repo)
                if ci_tool is not None:
                    ci_found = ci_tool
                    break

            if ci_found:
                merged_df.at[index, 'continuous_integration'] = True
                merged_df.at[index, 'ci_tool'] = ci_found
            else:
                merged_df.at[index, 'continuous_integration'] = False
                # empty string for "checked but none found"
                merged_df.at[index, 'ci_tool'] = ""

            processed_count += 1
            print(f"Repositories completed: {processed_count}")

            # Persist progress after each repository
            merged_df.to_csv(output_csv_file, index=False)

        except GithubException as github_exception:
            handle_rate_limit_error(github_exception)
            print(f"Error accessing repository {owner_repo}: {github_exception}")
            # Mark as NA for errors (do not drop)
            merged_df.at[index, 'continuous_integration'] = pd.NA
            merged_df.at[index, 'ci_tool'] = pd.NA
            merged_df.to_csv(output_csv_file, index=False)
            continue

    # Final save
    merged_df.to_csv(output_csv_file, index=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Check for CI tools in GitHub repositories.')
    parser.add_argument(
        '--input',
        default='../collect_repositories/results/repositories_filtered.csv',
        help='Input CSV file containing repository URLs in "html_url" column'
    )
    parser.add_argument(
        '--output',
        default='results/soft_dev_pract.csv',
        help='Output CSV file to save the analysis results'
    )
    args = parser.parse_args()

    main(args.input, args.output)
