"""
Checks GitHub repositories for the presence of a .pre-commit-config.yaml
file and logs results to a CSV.

Usage: Navigate to the `collect_variables` directory and run:
    python3 scripts/soft_dev_pract/ci_practices/check_pre_commit_hooks.py \
    --input results/repository_links.csv --output results/ci_hooks.csv
"""

import argparse
import logging
import os
import time
from typing import Optional, List, Tuple, Set

import pandas as pd
from pandas.errors import EmptyDataError, ParserError
from github import Github, GithubException, RateLimitExceededException
from dotenv import load_dotenv
from urllib.parse import urlparse

# Constants
RATE_LIMIT_SLEEP_MINUTES = 20
GITHUB_HOSTS = ("https://github.com", "http://github.com")  
PRECOMMIT_FILE = ".pre-commit-config.yaml"

# Load .env file relative to this script
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
ENV_PATH = os.path.join(SCRIPT_DIR, "..", "..", "..", "..", ".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)

logger = logging.getLogger(__name__)


def _parse_github_owner_repo(html_url: str) -> Optional[Tuple[str, str]]:
    """
    Normalize and parse a GitHub URL into (owner, repo).

    Accepts:
      - http(s)://github.com/owner/repo
      - http(s)://www.github.com/owner/repo
      - github.com/owner/repo
      - www.github.com/owner/repo

    Returns:
      (owner, repo) on success, else None for non-GitHub or malformed URLs.
    """
    url = str(html_url).strip()

    # Add scheme for bare domains
    if url.startswith("github.com/") or url.startswith("www.github.com/"):
        url = "https://" + url

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    if host not in {"github.com", "www.github.com"}:
        return None

    # Path like "/owner/repo[/...]"
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None

    owner, repo_name = parts[0], parts[1]
    # strip trailing .git if present
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]

    return owner, repo_name


def check_ci_hook(html_url: str, github_instance: Github) -> str:
    """
    Check if `.pre-commit-config.yaml` exists in the root of a GitHub repository.

    Args:
        html_url: The repository URL.
        github_instance: Authenticated GitHub instance.

    Returns:
        One of: 'Present', 'Not Present', 'Not Supported', or 'Error'.
    """
    owner_repo = _parse_github_owner_repo(html_url)
    if owner_repo is None:
        return "Not Supported"

    owner, repo_name = owner_repo
    result = "Error"  # Default if something goes wrong

    # Retry loop for rate limits; avoids recursion and extra returns
    while True:
        try:
            repo = github_instance.get_repo(f"{owner}/{repo_name}")
            contents = repo.get_contents("/")
            found = any(content.name == PRECOMMIT_FILE for content in contents)
            result = "Present" if found else "Not Present"
            break

        except RateLimitExceededException:
            logger.warning(
                "Rate limit exceeded. Sleeping for %d minutes...",
                RATE_LIMIT_SLEEP_MINUTES,
            )
            time.sleep(RATE_LIMIT_SLEEP_MINUTES * 60)
            continue  # try again after sleeping

        except GithubException as exc:
            logger.error("GitHub API error for %s: %s", html_url, exc)
            result = "Error"
            break

        except (ValueError, TypeError, OSError) as exc:
            # Defensive: unexpected data shape/types or local OS issues
            logger.error("Unexpected data/OS error for %s: %s", html_url, exc)
            result = "Error"
            break

    return result


def _read_input_csv(path: str) -> Optional[pd.DataFrame]:
    """
    Read the input CSV, logging an error and returning None on failure.

    Args:
        path: Path to the CSV file.

    Returns:
        DataFrame or None on error.
    """
    try:
        return pd.read_csv(path)
    except (FileNotFoundError, PermissionError) as exc:
        logger.error("Error reading input file %s: %s", path, exc)
        return None
    except (EmptyDataError, ParserError, UnicodeDecodeError, ValueError) as exc:
        logger.error("Error parsing input file %s: %s", path, exc)
        return None
    except OSError as exc:
        logger.error("OS error reading input file %s: %s", path, exc)
        return None


def _load_existing_output(output_csv: str) -> Optional[pd.DataFrame]:
    """Load existing output CSV if it exists; return None otherwise."""
    try:
        if os.path.exists(output_csv):
            return pd.read_csv(output_csv)
    except Exception as exc:  # be tolerant; don't crash the run
        logger.error("Error reading existing output %s: %s", output_csv, exc)
    return None


def _outer_union_on_html_url(old_df: Optional[pd.DataFrame], new_df: pd.DataFrame) -> pd.DataFrame:
    """
    Outer-union old and new frames by 'html_url' without losing any columns/records.
    Prefer existing values where both have the same cell; fill gaps from new.
    """
    if old_df is None:
        return new_df.copy()

    if "html_url" not in old_df.columns or "html_url" not in new_df.columns:
        return new_df.copy()

    old_idx = old_df.set_index("html_url")
    new_idx = new_df.set_index("html_url")

    # Combine: keep existing values, fill with new
    combined = old_idx.combine_first(new_idx)

    # Also bring in any columns present only in the new df
    for col in new_idx.columns.difference(combined.columns):
        combined[col] = new_idx[col]

    return combined.reset_index()


def main(input_csv: str, output_csv: str) -> None:
    """
    Main logic to check repositories and save results.

    Args:
        input_csv: Path to input CSV containing an 'html_url' column.
        output_csv: Path for the output CSV to be written.
    """
    token = os.getenv("GITHUB_TOKEN")
    username = os.getenv("GITHUB_USERNAME")

    if not token or not username:
        logger.error("GitHub token or username not found in .env file.")
        return

    github_instance = Github(token)

    input_df = _read_input_csv(input_csv)
    if input_df is None:
        return

    if "html_url" not in input_df.columns:
        logger.error("Input file does not contain 'html_url' column.")
        return

    # Load existing output (if any) and union so no previous data is lost.
    existing_df = _load_existing_output(output_csv)
    merged_df = _outer_union_on_html_url(existing_df, input_df)

    # Prepare output column as nullable boolean: True/False/NA
    if "pre_commit" not in merged_df.columns:
        merged_df["pre_commit"] = pd.Series([pd.NA] * len(merged_df), dtype="boolean")
    else:
        # Ensure proper dtype (nullable boolean)
        merged_df["pre_commit"] = merged_df["pre_commit"].astype("boolean")

    # Process ONLY the repositories present in the current input
    to_process: Set[str] = set(map(str, input_df["html_url"].tolist()))
    skipped_urls: List[str] = []

    for idx, row in merged_df.iterrows():
        html_url = str(row["html_url"])
        if html_url not in to_process:
            continue  # keep prior result/data untouched

        logger.info("Processing: %s", html_url)

        result = check_ci_hook(html_url, github_instance)

        # Map to boolean/NA for CSV:
        #   Present -> True
        #   Not Present -> False
        #   Not Supported / Error -> <NA>  (empty cell)
        if result == "Present":
            merged_df.at[idx, "pre_commit"] = True
        elif result == "Not Present":
            merged_df.at[idx, "pre_commit"] = False
        else:
            merged_df.at[idx, "pre_commit"] = pd.NA
            skipped_urls.append(html_url)

    try:
        merged_df.to_csv(output_csv, index=False)
        logger.info("Results saved to %s", output_csv)

        skipped_file = output_csv.replace(".csv", "_skipped_urls.txt")
        with open(skipped_file, "w", encoding="utf-8") as out_f:
            for url in skipped_urls:
                out_f.write(f"{url}\n")
        logger.info("Skipped URLs saved to %s", skipped_file)

    except (PermissionError, OSError, ValueError) as exc:
        logger.error("Error saving output file(s): %s", exc)


def _build_arg_parser() -> argparse.ArgumentParser:
    """Create and return the argument parser."""
    parser = argparse.ArgumentParser(
        description="Check for .pre-commit-config.yaml in GitHub repositories."
    )
    parser.add_argument("--input", required=True, help="Path to input CSV file.")
    parser.add_argument("--output", required=True, help="Path to output CSV file.")
    return parser


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ARGS = _build_arg_parser().parse_args()
    main(ARGS.input, ARGS.output)
