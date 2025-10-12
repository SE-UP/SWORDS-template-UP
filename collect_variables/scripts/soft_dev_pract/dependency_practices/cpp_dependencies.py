"""
Scan C++ repos for explicit build/test artifacts in the repo ROOT:
- CMakeLists.txt
- *.cmake
- Makefile
- build.ninja
- CMakeCache.txt
- CMakeFiles/ (directory)

Requires input CSV with columns:
- html_url (GitHub repo URL)
- language (should include "C++" to be processed)

Adds columns:
- dependecy_explicit (bool)
- which_dependency (semicolon-separated names found)

Usage:
  python detect_dependencies_cpp.py --input path/to/input.csv --output path/to/output.csv
"""

import argparse
import csv
import os
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from dotenv import load_dotenv
from ghapi.all import GhApi
from requests.exceptions import RequestException
from fastcore.net import HTTPError as FastcoreHTTPError

# ---------- GitHub token via .env (per your layout) ----------
script_dir = os.path.dirname(os.path.realpath(__file__))
env_path = os.path.join(script_dir, "..", "..", "..", "..", ".env")
load_dotenv(dotenv_path=env_path, override=True)

token = os.getenv("GITHUB_TOKEN")
gh = GhApi(token=token)

TARGET_FILES = {
    "CMakeLists.txt",
    "Makefile",
    "build.ninja",
    "CMakeCache.txt",
}
TARGET_DIRS = {
    "CMakeFiles",  # we’ll detect as "CMakeFiles/"
}

def normalize_url(url: str) -> str:
    """Ensure URL has a scheme so urlparse works, and strip whitespace."""
    if not url:
        return ""
    u = url.strip()
    if "://" not in u:
        u = "https://" + u
    return u

def extract_github_full_name(html_url: str) -> Optional[str]:
    """
    Return 'owner/repo' if URL is a GitHub repo, else None.
    Handles http/https/www and trailing '.git'.
    """
    u = normalize_url(html_url)
    try:
        p = urlparse(u)
        host = (p.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if host != "github.com":
            return None
        parts = [seg for seg in (p.path or "").split("/") if seg]
        if len(parts) < 2:
            return None
        owner, repo = parts[0], parts[1]
        if repo.endswith(".git"):
            repo = repo[:-4]
        return f"{owner}/{repo}"
    except Exception:
        return None

def list_root(repo_full_name: str) -> Optional[List[Dict]]:
    """
    List root directory contents via GitHub API, with rate-limit handling.
    Returns list of items (dicts) or None on fatal error.
    """
    owner, repo = repo_full_name.split("/", 1)
    while True:
        try:
            return gh.repos.get_content(owner, repo, path="")
        except (RequestException, FastcoreHTTPError) as exc:
            msg = str(exc).lower()
            if "rate limit" in msg:
                print("[rate-limit] Sleeping 20 minutes...")
                time.sleep(20 * 60)
                continue
            print(f"[error] Unable to list root for {repo_full_name}: {exc}")
            return None

def scan_root_for_dependencies(repo_full_name: str) -> Tuple[bool, List[str]]:
    """
    Check the repo ROOT for dependency/build artifacts.
    Returns (found_any, found_names)
    """
    items = list_root(repo_full_name)
    if items is None:
        # error already logged by list_root
        return False, []

    found: List[str] = []
    file_names = set()
    dir_names = set()

    for it in items:
        # GitHub API returns 'file' or 'dir'
        t = it.get("type", "")
        name = it.get("name", "")
        if not name:
            continue
        if t == "file":
            file_names.add(name)
            if name in TARGET_FILES:
                found.append(name)
            if name.endswith(".cmake"):
                found.append(name)  # include explicit .cmake modules at root
        elif t == "dir":
            dir_names.add(name)
            if name in TARGET_DIRS:
                found.append(name + "/")  # make the directory obvious

    return (len(found) > 0), sorted(found)

def get_col(row: Dict, *candidates: str) -> Optional[str]:
    """Fetch a column value by trying several possible names (case-insensitive)."""
    # Build map of lower->actual keys
    lower_map = {k.lower(): k for k in row.keys()}
    for cand in candidates:
        key = lower_map.get(cand.lower())
        if key is not None:
            return row.get(key)
    return None

def process_csv(input_file: str, output_file: str) -> None:
    if os.path.abspath(input_file) == os.path.abspath(output_file):
        raise ValueError("Refusing to overwrite input file. Choose a different --output path.")

    with open(input_file, newline="", encoding="utf-8") as inf:
        reader = csv.DictReader(inf)
        base_fields = reader.fieldnames or []
        # Append new columns (keep original order)
        fieldnames = base_fields + ["dependecy_explicit", "which_dependency"]

        results: List[Dict] = []
        for i, row in enumerate(reader, 1):
            url = get_col(row, "html_url", "html url") or ""
            language = get_col(row, "language", "Language") or ""

            # Default: preserve row, add empty/false values
            row_out = dict(row)  # copy so we don’t mutate the reader’s row
            row_out["dependecy_explicit"] = ""
            row_out["which_dependency"] = ""

            # Log which row we’re processing
            print(f"[{i}] Processing: {url!r} | language={language!r}")

            # Only consider C++
            if not isinstance(language, str) or "c++" not in language.lower():
                # Not C++ → keep row, but leave new columns empty
                results.append(row_out)
                continue

            # Must be GitHub to scan via API
            full = extract_github_full_name(url or "")
            if not full:
                print(f"    -> Skipping (non-GitHub or malformed URL)")
                results.append(row_out)
                continue

            print(f"    -> GitHub repo: {full} (root scan)")
            found_any, found_names = scan_root_for_dependencies(full)

            # Fill outputs
            row_out["dependecy_explicit"] = bool(found_any)
            row_out["which_dependency"] = "; ".join(found_names)

            results.append(row_out)

    # Write results (overwrites the output file, preserves all input columns)
    with open(output_file, "w", newline="", encoding="utf-8") as outf:
        writer = csv.DictWriter(outf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"Done. Wrote {len(results)} rows to {output_file}")

def main() -> None:
    ap = argparse.ArgumentParser(description="Detect explicit build/test artifacts in C++ GitHub repos (root only).")
    ap.add_argument("--input", required=True, help="Path to input CSV (must contain html_url/html url and language/Language).")
    ap.add_argument("--output", required=True, help="Path to output CSV (will be created/overwritten).")
    args = ap.parse_args()
    process_csv(args.input, args.output)

if __name__ == "__main__":
    main()
