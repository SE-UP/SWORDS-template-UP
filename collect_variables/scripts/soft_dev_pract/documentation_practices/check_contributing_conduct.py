"""
Checks GitHub repositories for CONTRIBUTING and CODE_OF_CONDUCT files
and saves the results to a CSV.

Usage: navigate to the repository root and run:
   python scripts/soft_dev_pract/documentation_practices/check_contributing_conduct.py
     --input results/repositories.csv --output results/output_results.csv
"""
from __future__ import annotations

import argparse
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Tuple

import pandas as pd
from dotenv import load_dotenv
from ghapi.all import GhApi
from requests.exceptions import HTTPError, RequestException
from pandas.errors import EmptyDataError, ParserError

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 10
DEFAULT_MAX_THREADS = 5


def load_credentials() -> Tuple[str, str]:
    """
    Load GITHUB_USER and GITHUB_TOKEN from the .env file located
    relative to the script's directory.

    Returns:
        (user, token)
    """
    script_dir = os.path.dirname(os.path.realpath(__file__))
    env_path = os.path.join(script_dir, "..", "..", "..", "..", ".env")
    load_dotenv(dotenv_path=env_path, override=True)
    user = os.getenv("GITHUB_USER")
    token = os.getenv("GITHUB_TOKEN")
    if not user or not token:
        raise ValueError(
            "GITHUB_USER or GITHUB_TOKEN not found. "
            "Please ensure the .env file is properly configured."
        )
    return user, token


def check_repository_files(
    api: GhApi, repo_owner: str, repo_name: str, target_file: str
) -> bool:
    """
    Check if a repository contains a specific file.

    Args:
        api: Authenticated GhApi instance.
        repo_owner: Repository owner.
        repo_name: Repository name.
        target_file: File path to check.

    Returns:
        True if file exists, False otherwise.
    """
    try:
        api.repos.get_content(owner=repo_owner, repo=repo_name, path=target_file)
        return True
    except HTTPError as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 404:
            return False
        raise
    except RequestException as exc:
        logger.error(
            "Network error checking %s/%s:%s -> %s",
            repo_owner,
            repo_name,
            target_file,
            exc,
        )
        return False


def check_rate_limit(api: GhApi) -> bool:
    """
    Check if the GitHub API rate limit has been reached. If exceeded, sleep
    until reset.

    Args:
        api: Authenticated GhApi instance.

    Returns:
        True if slept due to rate limiting, False otherwise.
    """
    rate_limit = api.rate_limit.get()
    remaining = rate_limit.resources.core.remaining
    reset_time = rate_limit.resources.core.reset

    if remaining == 0:
        current_time = time.time()
        sleep_time = max(0, reset_time - current_time + 60)
        logger.info(
            "Rate limit reached. Sleeping for ~%d minutes...", int(sleep_time // 60)
        )
        time.sleep(sleep_time)
        return True
    return False


def process_repository(api: GhApi, row: pd.Series) -> Tuple[Optional[bool], Optional[bool]]:
    """
    Process a single repository: Check for CONTRIBUTING and CODE_OF_CONDUCT files.

    Args:
        api: Authenticated GhApi instance.
        row: DataFrame row with 'html_url'.

    Returns:
        (has_contributing, has_code_of_conduct)
    """
    html_url = row.get("html_url")
    if not isinstance(html_url, str) or "github.com" not in html_url:
        return None, None

    parts = html_url.replace("https://github.com/", "").split("/")
    if len(parts) < 2:
        return None, None
    repo_owner, repo_name = parts[0], parts[1]

    contributing_paths = [
        "CONTRIBUTING.md",
        ".github/CONTRIBUTING.md",
        "docs/CONTRIBUTING.md",
    ]
    conduct_paths = [
        "CODE_OF_CONDUCT.md",
        ".github/CODE_OF_CONDUCT.md",
        "docs/CODE_OF_CONDUCT.md",
    ]

    try:
        has_contributing = any(
            check_repository_files(api, repo_owner, repo_name, path)
            for path in contributing_paths
        )
        has_code_of_conduct = any(
            check_repository_files(api, repo_owner, repo_name, path)
            for path in conduct_paths
        )
        return has_contributing, has_code_of_conduct
    except HTTPError as exc:
        logger.error("HTTP error for repo %s: %s", html_url, exc)
        return None, None
    except RequestException as exc:
        logger.error("Network error for repo %s: %s", html_url, exc)
        return None, None


def _read_input_csv(path: str) -> Optional[pd.DataFrame]:
    """
    Read the input CSV; try UTF-8 then ISO-8859-1.

    Args:
        path: Path to the CSV file.

    Returns:
        DataFrame on success; None on failure.
    """
    try:
        return pd.read_csv(path, delimiter=";", encoding="utf-8")
    except UnicodeDecodeError:
        logger.warning("UTF-8 failed for %s. Trying ISO-8859-1...", path)
        try:
            return pd.read_csv(path, delimiter=";", encoding="ISO-8859-1")
        except (
            FileNotFoundError,
            PermissionError,
            EmptyDataError,
            ParserError,
            UnicodeDecodeError,
            ValueError,
            OSError,
        ) as exc:
            logger.error("Failed to read %s: %s", path, exc)
            return None


def _ensure_output_columns(data_frame: pd.DataFrame) -> None:
    """
    Ensure result columns exist in DataFrame.

    Args:
        data_frame: DataFrame to modify.

    Returns:
        None
    """
    if "has_contributing" not in data_frame.columns:
        data_frame["has_contributing"] = None
    if "has_code_of_conduct" not in data_frame.columns:
        data_frame["has_code_of_conduct"] = None


def _submit_tasks(
    api: GhApi,
    data_frame: pd.DataFrame,
    executor: ThreadPoolExecutor,
) -> dict:
    """
    Submit processing tasks and return a future->index map.

    Args:
        api: Authenticated GhApi instance.
        data_frame: Input DataFrame.
        executor: ThreadPoolExecutor to submit tasks.

    Returns:
        Mapping of Future to row index.
    """
    future_to_index: dict = {}
    for index, row in data_frame.iterrows():
        if check_rate_limit(api):
            logger.info("Rate limit reset. Continuing...")
        if (
            pd.notnull(data_frame.at[index, "has_contributing"])
            and pd.notnull(data_frame.at[index, "has_code_of_conduct"])
        ):
            continue
        logger.info("Submitting: %s (index %d)", row.get("html_url"), index)
        future = executor.submit(process_repository, api, row)
        future_to_index[future] = index
    return future_to_index


def _handle_future_result(
    data_frame: pd.DataFrame,
    index: int,
    result: Tuple[Optional[bool], Optional[bool]],
) -> None:
    """
    Apply a single future result to the DataFrame.

    Args:
        data_frame: DataFrame to update.
        index: Row index.
        result: Tuple of (has_contributing, has_code_of_conduct).

    Returns:
        None
    """
    has_contributing, has_code_of_conduct = result
    data_frame.at[index, "has_contributing"] = has_contributing
    data_frame.at[index, "has_code_of_conduct"] = has_code_of_conduct


def process_repositories(
    input_csv: str,
    output_csv: str,
    user: str,
    token: str,
    max_threads: int = DEFAULT_MAX_THREADS,
) -> None:
    """
    Processes repositories with partial saving and parallel processing.

    Args:
        input_csv: Path to input CSV.
        output_csv: Output CSV path.
        user: GitHub user.
        token: GitHub token.
        max_threads: Max number of threads to use.
    """
    data_frame = _read_input_csv(input_csv)
    if data_frame is None:
        return

    if "html_url" not in data_frame.columns:
        logger.error("The 'html_url' column is missing in the input CSV file.")
        return

    _ensure_output_columns(data_frame)

    api = GhApi(owner=user, token=token)
    total_repos = len(data_frame)
    completed = 0

    with ThreadPoolExecutor(max_threads) as executor:
        future_to_index = _submit_tasks(api, data_frame, executor)

        for future in as_completed(future_to_index):
            index = future_to_index[future]
            result = future.result()
            _handle_future_result(data_frame, index, result)

            completed += 1
            logger.info("Processed: %d/%d", completed, total_repos)

            if completed % DEFAULT_BATCH_SIZE == 0:
                data_frame.to_csv(output_csv, index=False)
                logger.info("Partial results saved at %d/%d", completed, total_repos)

    data_frame.to_csv(output_csv, index=False)
    logger.info("Final results saved to %s", output_csv)


def main() -> None:
    """
    Parse CLI args and run.
    """
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    user, token = load_credentials()
    parser = argparse.ArgumentParser(
        description=(
            "Check for CONTRIBUTING.md and CODE_OF_CONDUCT.md in GitHub repositories."
        )
    )
    parser.add_argument("--input", required=True, help="Path to the input CSV file.")
    parser.add_argument("--output", required=True, help="Path to the output CSV file.")
    args = parser.parse_args()
    process_repositories(args.input, args.output, user, token)


if __name__ == "__main__":
    main()
