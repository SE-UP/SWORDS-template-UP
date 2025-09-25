"""
Analyze GitHub repositories for the presence of brief comments at the start
of source code files (.py, .R, .cpp). Results are written to a CSV.

Usage: Navigate to the 'collect_variables' directory and run:
   python scripts/soft_dev_pract/documentation_practices/check_contributing_conduct.py \
     --input results/repositories.csv --output results/output_results.csv
"""

import argparse
import logging
import os
import time
from collections.abc import Iterable
from typing import List, Mapping, Optional, Tuple

import pandas as pd
import requests
from dotenv import load_dotenv
from ghapi.all import GhApi
from pandas.errors import EmptyDataError, ParserError
from requests.exceptions import HTTPError, RequestException, Timeout

REQUEST_TIMEOUT_SECONDS = 10
RATE_LIMIT_SLEEP_SECONDS = 15 * 60
SUPPORTED_LANGUAGES = ("Python", "R", "C++")
GITHUB_PREFIX = "https://github.com/"
SOURCE_EXTENSIONS = (".py", ".R", ".cpp")
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
ENV_PATH = os.path.join(SCRIPT_DIR, "..", "..", "..", "..", ".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)

TOKEN = os.getenv("GITHUB_TOKEN")
API = GhApi(token=TOKEN)


def fetch_repository_files(repo_name: str, headers: Mapping[str, str]) -> List[str]:
    """
    Recursively fetch raw file download URLs for selected source files in a repo.

    Args:
        repo_name: 'owner/repo' repository slug.
        headers: HTTP headers (e.g., Authorization).

    Returns:
        List of raw file download URLs (.py, .R, .cpp).
    """
    repo_files: List[str] = []
    api_url = f"https://api.github.com/repos/{repo_name}/contents"

    def get_files(url: str) -> None:
        """
        Recursively traverse a GitHub repository directory (Contents API) and
        collect raw download URLs for matching source files.

        Args:
            url: GitHub Contents API directory URL to traverse.
        """
        try:
            response = requests.get(
                url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status()
        except (Timeout, RequestException) as exc:
            logger.error("Failed to fetch files from %s: %s", url, exc)
            return

        try:
            items = response.json()
        except ValueError as exc:
            logger.error("Non-JSON response at %s: %s", url, exc)
            return

        if not isinstance(items, Iterable):
            logger.error("Unexpected JSON structure at %s", url)
            return

        for item in items:
            try:
                item_type = item.get("type")
                name = item.get("name", "")
                if item_type == "file" and name.endswith(SOURCE_EXTENSIONS):
                    download_url = item.get("download_url")
                    if isinstance(download_url, str):
                        repo_files.append(download_url)
                elif item_type == "dir":
                    next_url = item.get("url")
                    if isinstance(next_url, str):
                        get_files(next_url)
            except AttributeError:
                logger.warning("Skipping malformed item at %s", url)

    get_files(api_url)
    return repo_files


def check_comment_at_start(file_url: str, headers: Mapping[str, str]) -> bool:
    """
    Check if a file has a comment at the very start.

    Args:
        file_url: Raw download URL of the file.
        headers: HTTP headers (e.g., Authorization).

    Returns:
        True if first line appears to be a comment; otherwise False.
    """
    try:
        response = requests.get(
            file_url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
    except (Timeout, RequestException) as exc:
        logger.error("Failed to fetch file %s: %s", file_url, exc)
        return False

    content = response.text
    lines = content.split("\n")
    if not lines:
        return False

    first_line = lines[0].strip()
    # Basic prefixes to capture common comment/docstring starts
    prefixes = ("#", "//", "/*", "'''", '"""')
    return any(first_line.startswith(prefix) for prefix in prefixes)


def determine_comment_category(percentage: float) -> str:
    """
    Map a percentage to a category label.

    Args:
        percentage: Percentage [0, 100].

    Returns:
        'most' (>75), 'more' (50–75], 'some' (25–50], or 'none' (≤25).
    """
    if percentage > 75:
        return "most"
    if 50 < percentage <= 75:
        return "more"
    if 25 < percentage <= 50:
        return "some"
    return "none"


def _sleep_if_rate_limited() -> None:
    """
    Sleep if the GitHub REST API core rate limit is exhausted.
    """
    try:
        rate_limit = API.rate_limit.get()
        # GhApi may return attrs rather than a dict; be defensive.
        resources = getattr(rate_limit, "resources", None)
        if isinstance(resources, dict):
            core = resources.get("core", {})
            remaining = int(core.get("remaining", 0) or 0)
        else:
            # Fallback: try dict-like access if available
            try:
                remaining = int(rate_limit["resources"]["core"]["remaining"])  # type: ignore[index]
            except Exception:  # pylint: disable=broad-except
                logger.warning("Could not read rate limit info (unexpected shape).")
                return

        if remaining == 0:
            logger.info(
                "Rate limit exceeded. Sleeping for %d minutes.",
                RATE_LIMIT_SLEEP_SECONDS // 60,
            )
            time.sleep(RATE_LIMIT_SLEEP_SECONDS)
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Could not read rate limit info: %s", exc)


def process_repository(
    repo_url: str, headers: Mapping[str, str]
) -> Tuple[Optional[float], Optional[str]]:
    """
    Process a single repository: collect source files and compute comment stats.

    Args:
        repo_url: Full GitHub repo URL (e.g., https://github.com/owner/repo).
        headers: HTTP headers (e.g., Authorization).

    Returns:
        (comment_percentage, comment_category) or (None, None) if unsupported or failed.
    """
    comment_percentage: Optional[float] = None
    comment_category: Optional[str] = None

    if not repo_url.startswith(GITHUB_PREFIX):
        logger.warning("Skipping non-GitHub URL: %s", repo_url)
        return comment_percentage, comment_category

    slug = repo_url.split(GITHUB_PREFIX, maxsplit=1)[-1].strip("/")
    parts = slug.split("/")
    if len(parts) < 2:
        logger.error("Malformed repository URL: %s", repo_url)
        return comment_percentage, comment_category

    owner, repo = parts[0], parts[1]

    _sleep_if_rate_limited()

    language: Optional[str] = None
    try:
        repo_info = API.repos.get(owner, repo)
        language = getattr(repo_info, "language", None)
    except HTTPError as exc:
        logger.error("HTTP error fetching repo info for %s: %s", slug, exc)
    except RequestException as exc:
        logger.error("Request error fetching repo info for %s: %s", slug, exc)

    if language not in SUPPORTED_LANGUAGES:
        if language is not None:
            logger.info("Skipping %s due to unsupported language: %s", slug, language)
        return comment_percentage, comment_category

    repo_files = fetch_repository_files(slug, headers)
    total_files = len(repo_files)
    if total_files == 0:
        logger.info("No matching source files found in %s", slug)
        comment_percentage = 0.0
        comment_category = "none"
        return comment_percentage, comment_category

    commented_files = 0
    for file_url in repo_files:
        try:
            if check_comment_at_start(file_url, headers):
                commented_files += 1
        except (RequestException, Timeout) as exc:
            logger.error("Error checking %s: %s", file_url, exc)

    comment_percentage = (commented_files / total_files) * 100.0
    comment_category = determine_comment_category(comment_percentage)
    return comment_percentage, comment_category


def _read_input_csv(path: str) -> Optional[pd.DataFrame]:
    """
    Read the input CSV defensively.

    Args:
        path: Path to the CSV file.

    Returns:
        DataFrame on success; None on failure.
    """
    try:
        return pd.read_csv(
            path,
            sep=";",
            encoding="ISO-8859-1",
            on_bad_lines="warn",
        )
    except (FileNotFoundError, PermissionError) as exc:
        logger.error("Cannot read input file %s: %s", path, exc)
    except (EmptyDataError, ParserError, UnicodeDecodeError, ValueError) as exc:
        logger.error("Parsing error reading %s: %s", path, exc)
    except OSError as exc:
        logger.error("OS error reading %s: %s", path, exc)
    return None


def _save_csv_safely(data_frame: pd.DataFrame, path: str) -> None:
    """
    Save a DataFrame to CSV with narrowed exception handling.

    Args:
        data_frame: The DataFrame to save.
        path: Output CSV path.
    """
    try:
        data_frame.to_csv(path, index=False)
    except (PermissionError, OSError, ValueError) as exc:
        logger.error("Failed to write results to %s: %s", path, exc)


def _process_row(
    data_frame: pd.DataFrame,
    index: int,
    total: int,
    headers: Mapping[str, str],
    output_csv: str,
) -> None:
    """
    Process a single CSV row and persist progress.

    Args:
        data_frame: DataFrame holding repository rows.
        index: Row index.
        total: Total number of rows.
        headers: HTTP headers (e.g., Authorization).
        output_csv: Path for interim progress saves.
    """
    repo_url = data_frame.at[index, "html_url"]
    logger.info("Processing repository %d/%d: %s", index + 1, total, repo_url)

    try:
        pct, cat = process_repository(repo_url, headers)
    except (HTTPError, RequestException, Timeout) as exc:
        logger.error("Network/API error for %s: %s", repo_url, exc)
        return
    except (KeyError, TypeError, ValueError) as exc:
        logger.error("Data error for %s: %s", repo_url, exc)
        return

    if pct is not None and cat is not None:
        data_frame.at[index, "comment_percentage"] = pct
        data_frame.at[index, "comment_category"] = cat

    _save_csv_safely(data_frame, output_csv)


def analyze_repositories(input_csv: str, output_csv: str) -> None:
    """
    Analyze repositories listed in the input CSV and write results to output CSV.

    Args:
        input_csv: Path to the input CSV containing 'html_url' column.
        output_csv: Path to the CSV to write results.
    """
    if not isinstance(TOKEN, str) or not TOKEN:
        logger.error("GITHUB_TOKEN not found. Set it in your .env file.")
        return

    headers: Mapping[str, str] = {"Authorization": f"token {TOKEN}"}
    data_frame = _read_input_csv(input_csv)
    if data_frame is None:
        return

    if "html_url" not in data_frame.columns:
        logger.error('Input file does not contain required "html_url" column.')
        return

    if "comment_percentage" not in data_frame.columns:
        data_frame["comment_percentage"] = 0.0
    if "comment_category" not in data_frame.columns:
        data_frame["comment_category"] = ""

    total_repos = len(data_frame)

    for idx, _row in data_frame.iterrows():
        _process_row(data_frame, idx, total_repos, headers, output_csv)

    _save_csv_safely(data_frame, output_csv)
    logger.info("Results saved to %s", output_csv)


def _build_arg_parser() -> argparse.ArgumentParser:
    """
    Build and return the CLI argument parser.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Analyze GitHub repositories for comments at the start of files."
        )
    )
    parser.add_argument(
        "--input",
        default="../collect_repositories/results/repositories_filtered.csv",
        help=('Input CSV file containing repository URLs in "html_url" column'),
    )
    parser.add_argument(
        "--output",
        default="results/soft_dev_pract.csv",
        help="Output CSV file to save the analysis results",
    )
    return parser


def main() -> None:
    """
    Entry point for CLI execution.
    """
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    args = _build_arg_parser().parse_args()
    analyze_repositories(args.input, args.output)


if __name__ == "__main__":
    main()
