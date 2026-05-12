import argparse
import logging
import os
import time
import re
import base64
from typing import Optional, List, Tuple, Set, Dict

import pandas as pd
from pandas.errors import EmptyDataError, ParserError
from github import Github, GithubException, RateLimitExceededException
from dotenv import load_dotenv
from urllib.parse import urlparse

# Constants
RATE_LIMIT_SLEEP_MINUTES = 20
PRECOMMIT_FILE = ".pre-commit-config.yaml"

# Load .env file relative to this script
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
# Note: Adjust the number of ".." if your .env is in a different relative location
ENV_PATH = os.path.join(SCRIPT_DIR, "..", "..", "..", "..", ".env")
load_dotenv(dotenv_path=ENV_PATH, override=True)

logger = logging.getLogger(__name__)

# Canonical keyword -> regex (per language)
LANG_KEYWORDS: Dict[str, Dict[str, str]] = {
    "python": {
        "pytest": r"\bpytest\b",
    },
    "r": {
        "testthat": r"\btestthat\b",
        "tinytest": r"\btinytest\b",
        "rcmdcheck": r"R\s+CMD\s+check",
        "runit": r"\brunit\b",
    },
    "c++": {
        "ctest": r"\bctest\b",
        "gtest": r"\bgtest\b|\bgoogle\s*test\b",
        "catch2": r"\bcatch2\b|\bcatch\s*2\b",
    },
}

def _parse_github_owner_repo(html_url: str) -> Optional[Tuple[str, str]]:
    """Normalize and parse a GitHub URL into (owner, repo)."""
    url = str(html_url).strip()
    
    # Handle bare domains
    if url.startswith("github.com/") or url.startswith("www.github.com/"):
        url = "https://" + url

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    
    # Strictly allow only GitHub
    if host not in {"github.com", "www.github.com"}:
        return None

    # Path segments like ["owner", "repo"]
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None

    owner, repo_name = parts[0], parts[1]
    
    # Remove trailing .git if present
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]

    return owner, repo_name

def scan_file_content(content: str) -> Tuple[bool, List[str]]:
    """Scans file text for keywords and returns (found_any, list_of_keywords)."""
    found_keywords = []
    for lang, keywords in LANG_KEYWORDS.items():
        for key_name, pattern in keywords.items():
            if re.search(pattern, content, re.IGNORECASE):
                found_keywords.append(key_name)
    return len(found_keywords) > 0, found_keywords

def check_ci_hook_details(html_url: str, github_instance: Github) -> Dict:
    """Checks for .pre-commit-config.yaml and scans its content."""
    owner_repo = _parse_github_owner_repo(html_url)
    res = {"status": "Error", "has_tests": False, "keywords": []}

    if owner_repo is None:
        res["status"] = "Not Supported"
        return res

    owner, repo_name = owner_repo
    while True:
        try:
            repo = github_instance.get_repo(f"{owner}/{repo_name}")
            try:
                # Attempt to get file content directly
                file_content = repo.get_contents(PRECOMMIT_FILE)
                # GitHub returns content as base64 string
                decoded_content = base64.b64decode(file_content.content).decode("utf-8")
                
                has_tests, found_keys = scan_file_content(decoded_content)
                return {
                    "status": "Present", 
                    "has_tests": has_tests, 
                    "keywords": found_keys
                }
            except GithubException as e:
                if e.status == 404:
                    return {"status": "Not Present", "has_tests": False, "keywords": []}
                raise e
                
        except RateLimitExceededException:
            logger.warning("Rate limit exceeded. Sleeping for %d minutes...", RATE_LIMIT_SLEEP_MINUTES)
            time.sleep(RATE_LIMIT_SLEEP_MINUTES * 60)
            continue
        except Exception as exc:
            logger.error("GitHub API error for %s: %s", html_url, exc)
            return res

def _read_input_csv(path: str) -> Optional[pd.DataFrame]:
    """Safely read input CSV file."""
    try:
        return pd.read_csv(path)
    except Exception as exc:
        logger.error("Error reading input file %s: %s", path, exc)
        return None

def _load_existing_output(output_csv: str) -> Optional[pd.DataFrame]:
    """Load existing results if they exist to prevent data loss."""
    if os.path.exists(output_csv):
        try:
            return pd.read_csv(output_csv)
        except Exception as exc:
            logger.error("Error reading existing output %s: %s", output_csv, exc)
    return None

def _outer_union_on_html_url(old_df: Optional[pd.DataFrame], new_df: pd.DataFrame) -> pd.DataFrame:
    """Merge new data into existing records without losing previous columns."""
    if old_df is None or "html_url" not in old_df.columns:
        return new_df.copy()
    
    old_idx = old_df.set_index("html_url")
    new_idx = new_df.set_index("html_url")
    
    # Combine prefers values from the original file for existing cells
    combined = old_idx.combine_first(new_idx)
    
    # Ensure any brand new columns from input_df are included
    for col in new_idx.columns.difference(combined.columns):
        combined[col] = new_idx[col]
        
    return combined.reset_index()

def main(input_csv: str, output_csv: str) -> None:
    """Main execution logic."""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        logger.error("GitHub token not found in .env file.")
        return

    github_instance = Github(token)
    input_df = _read_input_csv(input_csv)
    
    if input_df is None or "html_url" not in input_df.columns:
        logger.error("Input file is missing or lacks 'html_url' column.")
        return

    # Load existing output and merge with new input to preserve all columns
    existing_df = _load_existing_output(output_csv)
    merged_df = _outer_union_on_html_url(existing_df, input_df)

    # Initialize new columns with nullable boolean types
    for col in ["pre_commit", "pre_commit_test"]:
        if col not in merged_df.columns:
            merged_df[col] = pd.Series([pd.NA] * len(merged_df), dtype="boolean")
        else:
            merged_df[col] = merged_df[col].astype("boolean")
    
    if "pre_commit_test_keyword" not in merged_df.columns:
        merged_df["pre_commit_test_keyword"] = ""

    # Only process URLs that are in the current input file
    to_process = set(map(str, input_df["html_url"].tolist()))
    skipped_urls = []

    for idx, row in merged_df.iterrows():
        url = str(row["html_url"])
        if url not in to_process:
            continue

        logger.info("Processing: %s", url)
        data = check_ci_hook_details(url, github_instance)

        if data["status"] == "Present":
            merged_df.at[idx, "pre_commit"] = True
            merged_df.at[idx, "pre_commit_test"] = data["has_tests"]
            merged_df.at[idx, "pre_commit_test_keyword"] = ", ".join(data["keywords"])
        elif data["status"] == "Not Present":
            merged_df.at[idx, "pre_commit"] = False
            merged_df.at[idx, "pre_commit_test"] = False
        else:
            # For "Not Supported" or "Error"
            merged_df.at[idx, "pre_commit"] = pd.NA
            skipped_urls.append(url)

    # Save final merged CSV
    try:
        merged_df.to_csv(output_csv, index=False)
        
        # Save skipped/failed URLs to a text file
        skipped_file = output_csv.replace(".csv", "_skipped_urls.txt")
        with open(skipped_file, "w", encoding="utf-8") as f:
            for s_url in skipped_urls:
                f.write(f"{s_url}\n")
                
        logger.info("Audit complete. Results: %s | Skipped: %s", output_csv, skipped_file)
    except Exception as e:
        logger.error("Failed to save output files: %s", e)

if __name__ == "__main__":
    # Configure logging to show time and priority level
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    
    parser = argparse.ArgumentParser(description="Deep scan GitHub pre-commit hooks for keywords.")
    parser.add_argument("--input", required=True, help="Path to input repository CSV.")
    parser.add_argument("--output", required=True, help="Path to save result CSV.")
    
    args = parser.parse_args()
    main(args.input, args.output)