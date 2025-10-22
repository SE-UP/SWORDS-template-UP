"""
CLI: scan GitHub repositories listed in an input CSV (column `html_url`) and
append dependency/test dependency signals without losing any original data.

- Skips non-GitHub URLs and logs them.
- Robust to missing Language column (infers from GitHub if needed).
- Outputs a CSV with all original columns plus:
    * dependencies_explicit (bool)
    * which_dependencies_file (str)
    * test_dependecy (bool)        # name preserved per request
    * which_test_dependency (str)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlparse

import pandas as pd
from dotenv import load_dotenv
from github import Github
from github.GithubException import GithubException, RateLimitExceededException

# ----------------------------- Constants ------------------------------------

SLEEP_MINUTES_ON_RATE_LIMIT = 20
RATE_LIMIT_POLL_SECS = 5

# Patterns to detect dependency files by language
DEPENDENCY_FILE_PATTERNS: Dict[str, List[str]] = {
    "Python": [
        # wildcard-like checks are done in code (startswith/endswith/contains)
        "requirements",      # requirements*.txt
        "pyproject.toml",
        ".lock",             # generic lock files (e.g., pipenv/PDM/poetry)
    ],
    "R": [
        "DESCRIPTION",
        "renv.lock",
    ],
    "C++": [
        "CMakeLists.txt",
        "Makefile",          # common spelling
        ".make",             # any file that endswith .make
        "vcpkg.json",
    ],
}

# Test libraries to search inside dependency files
TEST_DEPENDENCIES: Dict[str, List[str]] = {
    "Python": ["pytest", "unittest", "nose", "unnittest"],  # include common typo
    "R": ["testthat", "tinytest"],
    "C++": ["gtest", "ctest", "catch2"],
}

# Output columns (names per user request)
COL_DEP_EXPLICIT = "dependencies_explicit"
COL_WHICH_DEP = "which_dependencies_file"
COL_TEST_DEP = "test_dependecy"  # keep the exact spelling requested
COL_WHICH_TEST = "which_test_dependency"

# ----------------------------- Utilities ------------------------------------


def load_github_client() -> Github:
    """Load .env from the requested relative path and return an authenticated Github client."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(script_dir, "..", "..", "..", "..", ".env")
    load_dotenv(dotenv_path=env_path, override=True)

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        logging.error("GITHUB_TOKEN not found in .env at: %s", env_path)
        sys.exit(1)
    return Github(token)


def is_github_url(url: str) -> bool:
    """Return True if the URL points to github.com (with or without www)."""
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host == "github.com" and len(parsed.path.strip("/").split("/")) >= 2
    except Exception:
        return False


def repo_full_name_from_url(url: str) -> Optional[str]:
    """
    Convert a GitHub HTTPS URL to 'owner/repo'.
    Handles extra path segments (issues, tree, etc.) by taking first two.
    """
    try:
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2:
            owner, repo = parts[0], parts[1]
            # strip .git suffix if present
            if repo.endswith(".git"):
                repo = repo[:-4]
            return f"{owner}/{repo}"
    except Exception:
        return None
    return None


def wait_out_rate_limit(g: Github, sleep_minutes: int = SLEEP_MINUTES_ON_RATE_LIMIT) -> None:
    """Sleep when rate-limited. Prefer actual reset time if available; otherwise fixed minutes."""
    try:
        core = g.get_rate_limit().core
        reset_ts = core.reset.timestamp()
        now = time.time()
        wait_secs = max(int(reset_ts - now) + 1, sleep_minutes * 60)
        logging.warning("Rate limit reached. Sleeping for ~%s seconds.", wait_secs)
        time.sleep(wait_secs)
    except Exception:
        logging.warning("Rate limit handling fallback: sleeping %d minutes.", sleep_minutes)
        time.sleep(sleep_minutes * 60)


def ensure_rate_headroom(g: Github) -> None:
    """Poll until we have at least 1 remaining core request."""
    while True:
        try:
            core = g.get_rate_limit().core
            if core.remaining > 0:
                return
            logging.info("No remaining requests; polling again in %d seconds.", RATE_LIMIT_POLL_SECS)
            time.sleep(RATE_LIMIT_POLL_SECS)
        except RateLimitExceededException:
            wait_out_rate_limit(g)
        except Exception as exc:
            logging.warning("Error checking rate limit (%s). Sleeping briefly.", exc)
            time.sleep(RATE_LIMIT_POLL_SECS)


def infer_language_if_needed(g: Github, repo, existing_lang: Optional[str]) -> Optional[str]:
    """Use the CSV Language if present; else infer from GitHub languages and map to Python/R/C++ if dominant."""
    normalized = (existing_lang or "").strip()
    if normalized:
        # Map some common variants to canonical names
        if normalized.lower().startswith("python"):
            return "Python"
        if normalized.upper() in {"C++", "CPP"} or "c++" in normalized.lower():
            return "C++"
        if normalized.lower().startswith("r"):
            return "R"
        # If not one of the target languages, return as-is for check below
        return normalized

    # No language provided: query GitHub
    try:
        ensure_rate_headroom(g)
        langs = repo.get_languages()  # Dict[str, int]
        # choose the largest share language
        if not langs:
            return None
        top_lang = max(langs.items(), key=lambda kv: kv[1])[0]
        if top_lang.lower().startswith("python"):
            return "Python"
        if top_lang.lower() in {"c++", "c", "cpp"}:
            # treat C as not necessarily C++; prefer explicit C++ only
            return "C++" if top_lang.lower() in {"c++", "cpp"} else None
        if top_lang.lower() == "r":
            return "R"
        return None
    except RateLimitExceededException:
        wait_out_rate_limit(g)
        return infer_language_if_needed(g, repo, existing_lang)
    except GithubException as exc:
        logging.error("GitHub error inferring language: %s", exc)
        return None
    except Exception as exc:
        logging.error("Unexpected error inferring language: %s", exc)
        return None


def match_dependency_files_for_language(file_paths: Iterable[str], language: str) -> List[str]:
    """Return a list of file paths matching dependency patterns for the given language."""
    patterns = DEPENDENCY_FILE_PATTERNS.get(language, [])
    matches: List[str] = []
    for p in file_paths:
        filename = os.path.basename(p)
        lower = filename.lower()

        if language == "Python":
            if lower.startswith("requirements") and lower.endswith(".txt"):
                matches.append(p)
                continue
            if lower == "pyproject.toml":
                matches.append(p)
                continue
            if lower.endswith(".lock"):
                matches.append(p)
                continue

        elif language == "R":
            if filename == "DESCRIPTION":
                matches.append(p)
                continue
            if lower == "renv.lock":
                matches.append(p)
                continue

        elif language == "C++":
            if filename == "CMakeLists.txt":
                matches.append(p)
                continue
            if filename == "Makefile":
                matches.append(p)
                continue
            if lower.endswith(".make"):
                matches.append(p)
                continue
            if lower == "vcpkg.json":
                matches.append(p)
                continue

        # Generic fallback (unlikely to hit due to explicit checks)
        else:
            for pat in patterns:
                if pat.lower() in lower:
                    matches.append(p)
                    break

    # Deduplicate while keeping order
    seen: Set[str] = set()
    unique = []
    for m in matches:
        if m not in seen:
            unique.append(m)
            seen.add(m)
    return unique


def fetch_repo_tree_paths(g: Github, repo) -> List[str]:
    """Return all file paths in the default branch tree."""
    try:
        ensure_rate_headroom(g)
        default_branch = repo.default_branch
        ensure_rate_headroom(g)
        tree = repo.get_git_tree(default_branch, recursive=True).tree
        return [item.path for item in tree if item.type == "blob"]  # files only
    except RateLimitExceededException:
        wait_out_rate_limit(g)
        return fetch_repo_tree_paths(g, repo)
    except GithubException as exc:
        logging.error("GitHub error fetching tree: %s", exc)
        return []
    except Exception as exc:
        logging.error("Unexpected error fetching tree: %s", exc)
        return []


def read_file_text(g: Github, repo, path: str) -> str:
    """Read a text file from the repo, decoding as UTF-8 (ignore errors)."""
    try:
        ensure_rate_headroom(g)
        content = repo.get_contents(path)
        data = content.decoded_content
        return data.decode("utf-8", errors="ignore")
    except RateLimitExceededException:
        wait_out_rate_limit(g)
        return read_file_text(g, repo, path)
    except Exception as exc:
        logging.debug("Could not read file %s: %s", path, exc)
        return ""


def detect_test_dependencies(texts: List[str], language: str) -> Tuple[bool, List[str]]:
    """Search combined texts for known test dependencies for the given language."""
    terms = TEST_DEPENDENCIES.get(language, [])
    found: Set[str] = set()
    big = "\n".join(texts).lower()
    for t in terms:
        if t.lower() in big:
            found.add(t)
    return (len(found) > 0, sorted(found))


def process_repo(
    g: Github, html_url: str, csv_language: Optional[str]
) -> Tuple[bool, str, bool, str]:
    """
    Process a single repository URL.

    Returns:
        (dependencies_explicit, which_dependencies_file, test_dependecy, which_test_dependency)
    """
    if not is_github_url(html_url):
        logging.info("Skipping non-GitHub URL: %s", html_url)
        return (False, "", False, "")

    full_name = repo_full_name_from_url(html_url)
    if not full_name:
        logging.error("Could not parse owner/repo from URL: %s", html_url)
        return (False, "", False, "")

    logging.info("Processing %s (%s)", html_url, full_name)

    try:
        ensure_rate_headroom(g)
        repo = g.get_repo(full_name)
    except RateLimitExceededException:
        wait_out_rate_limit(g)
        return process_repo(g, html_url, csv_language)
    except GithubException as exc:
        logging.error("GitHub error getting repo %s: %s", full_name, exc)
        return (False, "", False, "")
    except Exception as exc:
        logging.error("Unexpected error getting repo %s: %s", full_name, exc)
        return (False, "", False, "")

    # Determine language of interest
    language = infer_language_if_needed(g, repo, csv_language)
    if language not in {"Python", "R", "C++"}:
        logging.info("Language not in target set (Python/R/C++). Detected: %s", language)
        return (False, "", False, "")

    # List files & match dependency files
    paths = fetch_repo_tree_paths(g, repo)
    dep_files = match_dependency_files_for_language(paths, language)
    dep_explicit = len(dep_files) > 0
    which_dep = ", ".join(dep_files)

    # Read dependency files and look for test libs
    texts = [read_file_text(g, repo, p) for p in dep_files]
    test_found, which_test_list = detect_test_dependencies(texts, language)
    which_test = ", ".join(which_test_list)

    return (dep_explicit, which_dep, test_found, which_test)


def configure_logging(log_file: str) -> None:
    """Configure logging to file and console."""
    fmt = "%(asctime)s | %(levelname)s | %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )


def add_output_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure output columns exist and are initialized so we never lose input data."""
    if COL_DEP_EXPLICIT not in df.columns:
        df[COL_DEP_EXPLICIT] = False
    if COL_WHICH_DEP not in df.columns:
        df[COL_WHICH_DEP] = ""
    if COL_TEST_DEP not in df.columns:
        df[COL_TEST_DEP] = False
    if COL_WHICH_TEST not in df.columns:
        df[COL_WHICH_TEST] = ""
    return df


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Scan GitHub repos from an input CSV and append dependency/test-dependency info."
    )
    parser.add_argument("--input", required=True, help="Path to input CSV (must include 'html_url').")
    parser.add_argument("--output", required=True, help="Path to output CSV (will be created/overwritten).")
    parser.add_argument(
        "--log-file", default="dependency_scan.log", help="Path to log file (default: dependency_scan.log)"
    )
    parser.add_argument(
        "--sleep-minutes",
        type=int,
        default=SLEEP_MINUTES_ON_RATE_LIMIT,
        help="Minutes to sleep when rate-limited (default: 20).",
    )

    args = parser.parse_args()
    configure_logging(args.log_file)


    # Load data
    try:
        df = pd.read_csv(args.input, sep=";", dtype=str, keep_default_na=False, encoding="utf-8-sig")

    except Exception as exc:
        logging.error("Failed to read input CSV: %s", exc)
        sys.exit(1)

    if "html_url" not in df.columns:
        logging.error("Input CSV must contain a column named 'html_url'.")
        sys.exit(1)

    df = add_output_columns(df)

    # GitHub client
    g = load_github_client()

    # Process each row (no data loss; we only add/modify our four columns)
    for idx, row in df.iterrows():
        url = str(row.get("html_url", "")).strip()
        lang_val = row.get("Language", None)  # may be missing

        if not url:
            logging.info("Row %s has empty html_url; skipping.", idx)
            continue

        try:
            dep_explicit, which_dep, test_dep, which_test = process_repo(g, url, lang_val)
            df.at[idx, COL_DEP_EXPLICIT] = bool(dep_explicit)
            df.at[idx, COL_WHICH_DEP] = which_dep
            df.at[idx, COL_TEST_DEP] = bool(test_dep)
            df.at[idx, COL_WHICH_TEST] = which_test
        except RateLimitExceededException:
            # Extra safety: if raised from deep call
            wait_out_rate_limit(g)
            # Retry once after sleeping
            try:
                dep_explicit, which_dep, test_dep, which_test = process_repo(g, url, lang_val)
                df.at[idx, COL_DEP_EXPLICIT] = bool(dep_explicit)
                df.at[idx, COL_WHICH_DEP] = which_dep
                df.at[idx, COL_TEST_DEP] = bool(test_dep)
                df.at[idx, COL_WHICH_TEST] = which_test
            except Exception as exc:  # noqa: BLE001
                logging.error("Failed after rate-limit wait for %s: %s", url, exc)
        except GithubException as exc:
            logging.error("GitHub error on %s: %s. Skipping.", url, exc)
        except Exception as exc:  # noqa: BLE001
            logging.error("Unexpected error on %s: %s. Skipping.", url, exc)

    # Write output (no loss of original columns)
    try:
        df.to_csv(args.output, index=False)
        logging.info("Wrote output CSV to %s", args.output)
    except Exception as exc:
        logging.error("Failed to write output CSV: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
