"""Check for *performance*/*benchmark*/*perf*/*bench* folders in root level of repository.

Command to execute: 
python check_perf_bench.py \
  --input path/to/input.csv \
  --output path/to/output.csv
"""
import argparse
import csv
import os
import time
from typing import Tuple

from dotenv import load_dotenv
from ghapi.all import GhApi
from requests.exceptions import RequestException
from fastcore.net import HTTPError as FastcoreHTTPError

# --- GitHub token handling (as requested) ---
script_dir = os.path.dirname(os.path.realpath(__file__))
env_path = os.path.join(script_dir, "..", "..", "..", "..", ".env")
load_dotenv(dotenv_path=env_path, override=True)

token = os.getenv("GITHUB_TOKEN")
gh = GhApi(token=token)

# Substring keys to match
PERF_BENCH_KEYS = ["performance", "benchmark", "bench", "perf"]


def is_github_url(url: str) -> bool:
    """
    Check whether a URL points to GitHub.

    Args:
        url: A URL string.

    Returns:
        True if the URL contains "github.com"; otherwise False.
    """
    u = (url or "").lower()
    return "github.com" in u


def normalize_repo_full_name(url: str) -> str:
    """
    Extract the "owner/repo" portion from a GitHub URL.

    Args:
        url: A GitHub repository URL.

    Returns:
        The repository full name in "owner/repo" format, or an empty string if not found.
    """
    if "github.com/" not in url:
        return ""
    return url.split("github.com/")[1].strip("/")


def sleep_with_countdown(seconds: int) -> None:
    """
    Sleep for the given duration while printing a remaining-minutes countdown.

    Args:
        seconds: Total number of seconds to sleep.

    Returns:
        None
    """
    remaining = seconds
    while remaining > 0:
        mins = remaining // 60
        print(f"Rate limit reached. Sleeping... {mins} minutes remaining")
        time.sleep(60)
        remaining -= 60


def check_perf_bench_folders(repo_full_name: str) -> Tuple[bool, str]:
    """
    Check for performance/benchmark folders at the repository root.

    Args:
        repo_full_name: Repository name in "owner/repo" format.

    Returns:
        A tuple (found, folder_name) where:
        - found is True if a perf/benchmark folder is detected.
        - folder_name is the detected folder name, or "" if not found.

    Raises:
        RequestException: If a network error occurs during the API call.
        FastcoreHTTPError: If GitHub API returns an HTTP error.
    """
    root_contents = gh.repos.get_content(*repo_full_name.split("/"), path="")
    for item in root_contents:
        if item.get("type") == "dir":
            name = item.get("name", "").lower()
            if any(key in name for key in PERF_BENCH_KEYS):
                return True, item.get("name", "")
    return False, ""


def analyze_repo(url: str) -> Tuple[bool, str]:
    """
    Analyze one repository URL for perf/benchmark folders.

    Args:
        url: Repository URL.

    Returns:
        A tuple (found, folder_name) where:
        - found is True if a perf/benchmark folder is detected.
        - folder_name is the detected folder name, or "" if not found.

    Raises:
        None. Errors are handled internally; rate limits trigger sleep and retry.
    """
    if not is_github_url(url):
        print(f"Skipping non-GitHub repository: {url}")
        return False, ""

    while True:
        try:
            repo_full_name = normalize_repo_full_name(url)
            if not repo_full_name or "/" not in repo_full_name:
                print(f"Skipping invalid GitHub URL: {url}")
                return False, ""

            return check_perf_bench_folders(repo_full_name)

        except RequestException as exc:
            msg = str(exc).lower()
            if "rate limit exceeded" in msg or "api rate limit exceeded" in msg:
                sleep_with_countdown(20 * 60)
                continue
            print(f"Network error processing repository {url}: {exc}")
            return False, ""

        except FastcoreHTTPError as exc:
            msg = str(exc).lower()
            if "rate limit" in msg:
                sleep_with_countdown(20 * 60)
                continue
            print(f"HTTP error processing repository {url}: {exc}")
            return False, ""


def process_csv(input_file: str, output_file: str) -> None:
    """
    Read input CSV, scan repos, and write output CSV with results.

    Args:
        input_file: Path to input CSV (must include column "html_ur").
        output_file: Path to output CSV.

    Returns:
        None

    Raises:
        ValueError: If required column "html_ur" is missing from the input CSV.
        OSError: If input/output files cannot be opened or written.
    """
    with open(input_file, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile, delimiter=",")
        if not reader.fieldnames or "html_ur" not in reader.fieldnames:
            raise ValueError("Required column not found in input CSV: html_ur")

        fieldnames = list(reader.fieldnames) + [
            "perf_bench_folder_found",
            "perf_bench_name",
        ]
        results = []

        for row in reader:
            url = row.get("html_ur", "")
            found, name = analyze_repo(url)
            row["perf_bench_folder_found"] = found
            row["perf_bench_name"] = name
            results.append(row)

    with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"Processing complete. Results saved to {output_file}.")


def main() -> None:
    """
    Parse CLI arguments and run the perf/benchmark folder scan.

    Args:
        None

    Returns:
        None

    Raises:
        SystemExit: If required CLI arguments are missing or invalid.
    """
    parser = argparse.ArgumentParser(
        description="Check for perf/benchmark folders at GitHub repo root."
    )
    parser.add_argument("--input", required=True, help="Path to input CSV file.")
    parser.add_argument("--output", required=True, help="Path to output CSV file.")
    args = parser.parse_args()
    process_csv(args.input, args.output)


if __name__ == "__main__":
    main()
