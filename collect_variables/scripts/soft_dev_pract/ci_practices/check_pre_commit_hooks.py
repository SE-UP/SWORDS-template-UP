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
from typing import Optional, List

import pandas as pd
from pandas.errors import EmptyDataError, ParserError
from github import Github, GithubException, RateLimitExceededException
from dotenv import load_dotenv

# Constants
RATE_LIMIT_SLEEP_MINUTES = 20
GITHUB_HOSTS = ("https://github.com", "http://github.com", "https://www.github.com", "http://www.github.com")
PRECOMMIT_FILE = ".pre-commit-config.yaml"

# Load .env file relative to this script
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
ENV_PATH = os.path.join(SCRIPT_DIR, "..", "..", "..", "..", ".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)

logger = logging.getLogger(__name__)


def check_ci_hook(html_url: str, github_instance: Github) -> str:
    """
    Check if `.pre-commit-config.yaml` exists in the root of a GitHub repository.

    Args:
        html_url: The repository URL.
        github_instance: Authenticated GitHub instance.

    Returns:
        One of: 'Present', 'Not Present', 'Not Supported', or 'Error'.
    """
    if not html_url.startswith(GITHUB_HOSTS):
        return "Not Supported"

    parts = html_url.rstrip("/").split("/")
    if len(parts) < 5:
        return "Error"

    owner, repo_name = parts[-2], parts[-1]
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

    data = _read_input_csv(input_csv)
    if data is None:
        return

    if "html_url" not in data.columns:
        logger.error("Input file does not contain 'html_url' column.")
        return

    data["ci_hook"] = ""
    skipped_urls: List[str] = []  # Py3.6–3.12 compatible

    for index, row in data.iterrows():
        html_url = row["html_url"]
        logger.info("Processing: %s", html_url)

        # Errors are handled in check_ci_hook and mapped to "Error"
        result = check_ci_hook(html_url, github_instance)
        data.at[index, "ci_hook"] = result

        if result in ("Error", "Not Supported"):
            skipped_urls.append(html_url)

    try:
        data.to_csv(output_csv, index=False)
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
