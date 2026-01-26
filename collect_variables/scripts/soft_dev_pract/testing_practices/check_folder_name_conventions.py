"""Checks types of testing in GitHub repositories by analyzing test folder (test/tests for python 
and test/testthat for R) names.

Usage: Navigate to the directory containing this script and run:
    python check_folder_name_conventions.py 
    --input path/to/input.csv --output path/to/output
"""
import argparse
import csv
import os
import time
from typing import List, Tuple, Optional

from dotenv import load_dotenv
from ghapi.all import GhApi
from requests.exceptions import RequestException
from fastcore.net import HTTPError as FastcoreHTTPError

script_dir = os.path.dirname(os.path.realpath(__file__))
env_path = os.path.join(script_dir, "..", "..", "..", "..", ".env")
load_dotenv(dotenv_path=env_path, override=True)

token = os.getenv("GITHUB_TOKEN")
gh = GhApi(token=token)

TEST_FOLDERS: List[str] = [
    "unit",
    "module",
    "component",
    "integration",
    "system",
    "e2e",
    "performance",
    "regression",
    "functional",
    "acceptance",
    "security",
    "sanity",
    "mutation",
    "metamorphic",
]

PYTHON_CPP_TEST_DIRS = ["test/", "tests/"]
R_TEST_DIRS = ["test/tinytest/", "test/testthat/", "tests/testthat/", "test/tinytest/"]


def search_test_folders(repo_full_name: str, lang: str) -> Tuple[List[str], List[str]]:
    """
    Search for test folders in a repository and return matching and non-matching subfolder names.

    Args:
        repo_full_name: The repository full name in the form "owner/repo".
        lang: The primary language of the repository in lowercase (e.g., "python", "r", "c++").

    Returns:
        A tuple of two lists:
        - A list of folder names that match known test categories.
        - A list of other folder names found under test directories.
    """
    print(f"Searching for test folders in repository: {repo_full_name}, Language: {lang}")
    found_folders: List[str] = []
    other_folders: List[str] = []

    try:
        root_contents = gh.repos.get_content(*repo_full_name.split("/"), path="")
        root_test_folders = [
            content["path"]
            for content in root_contents
            if content["type"] == "dir" and content["name"] in ["test", "tests"]
        ]

        for test_folder in root_test_folders:
            subcontents = gh.repos.get_content(*repo_full_name.split("/"), path=test_folder)
            for item in subcontents:
                if item["type"] == "dir":
                    if item["name"].lower() in TEST_FOLDERS:
                        found_folders.append(item["name"])
                    else:
                        other_folders.append(item["name"])
    except (RequestException, FastcoreHTTPError) as exc:
        print(f"Error searching folders in repository {repo_full_name}: {exc}")

    return list(set(found_folders)), list(set(other_folders))


def analyze_repo(url: str) -> Tuple[List[str], List[str]]:
    """
    Inspect a single repository URL and return its test and other folder names.

    Args:
        url: The repository HTML URL.

    Returns:
        A tuple of two lists:
        - A list of folder names that match known test categories.
        - A list of other folder names found under test directories.
    """
    test_folders: List[str] = []
    other_folders: List[str] = []

    if "github.com" not in url:
        print(f"Skipping non-GitHub repository: {url}")
        return test_folders, other_folders

    while True:
        try:
            repo_full_name = url.split("github.com/")[1].strip("/")
            repo = gh.repos.get(*repo_full_name.split("/"))
            lang: Optional[str] = repo["language"].lower() if repo["language"] else None

            if lang in ["python", "r", "c++"]:
                print(f"Checking repository: {repo_full_name}, Language: {lang}")
                test_folders, other_folders = search_test_folders(repo_full_name, lang)
            else:
                print(f"Skipping unsupported language ({lang}) in repository: {url}")
            break
        except RequestException as exc:
            msg = str(exc).lower()
            if "rate limit exceeded" in msg or "api rate limit exceeded" in msg:
                print("Rate limit reached. Sleeping for 20 minutes...")
                time.sleep(20 * 60)
                continue
            print(f"Network error processing repository {url}: {exc}")
            break
        except FastcoreHTTPError as exc:
            msg = str(exc).lower()
            if "rate limit" in msg:
                print("Rate limit exceeded. Sleeping for 20 minutes...")
                time.sleep(20 * 60)
                continue
            print(f"HTTP error processing repository {url}: {exc}")
            break

    return test_folders, other_folders


def process_csv(input_file: str, output_file: str) -> None:
    """
    Read repositories from a CSV, scan for test folder conventions, and write results to a CSV.

    Args:
        input_file: Path to the input CSV containing a column named "html_url".
        output_file: Path to the output CSV that will include "test_type" and
            "other_folders" columns.

    Returns:
        None
    """
    with open(input_file, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile, delimiter=",")
        fieldnames = (reader.fieldnames or []) + ["test_type", "other_folders"]
        results = []

        for row in reader:
            url = row.get("html_url", "")
            tests, others = analyze_repo(url)
            row["test_type"] = tests
            row["other_folders"] = others
            results.append(row)

    with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"Processing complete. Results saved to {output_file}.")


def main() -> None:
    """
    Parse command-line arguments and run the test folder convention analysis.

    Args:
        None

    Returns:
        None
    """
    parser = argparse.ArgumentParser(description="Check test folders in GitHub repositories.")
    parser.add_argument("--input", required=True, help="Path to input CSV file.")
    parser.add_argument("--output", required=True, help="Path to output CSV file.")
    args = parser.parse_args()
    process_csv(args.input, args.output)


if __name__ == "__main__":
    main()
