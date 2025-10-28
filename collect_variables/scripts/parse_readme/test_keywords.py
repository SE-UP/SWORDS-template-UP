#!/usr/bin/env python3
"""
Scan GitHub repos for testing-related keywords in top-level documentation.

Uses the Git Trees API (default branch) to list files, then fetches content via raw.githubusercontent.com.
- Scans root + first-level subfolders (non-recursive depth)
- Matches substrings: "test" and "testing" (case-insensitive)
- Adds columns: test_keyword_found, test_keyword_paths, docs_scanned_paths
- Filters to GitHub URLs and Language in {Python, R, C++}
- Sleeps 20 minutes on API rate limit; skips repos on error; logs progress
"""

import argparse
import os
import re
import sys
import time
import csv
from urllib.parse import urlparse
from typing import Optional, Tuple, List, Set

import pandas as pd
from dotenv import load_dotenv
from ghapi.all import GhApi
from fastcore.net import HTTPError

# ---------- Configuration ----------
KEYWORDS = ["test", "testing"]  # substring matches (broad)
DOC_EXTS = {
    ".md", ".markdown", ".mdown", ".mkdn", ".mkd",
    ".rst", ".adoc", ".asciidoc", ".txt"
}
TARGET_LANGUAGES = {"Python", "R", "C++"}
RATE_LIMIT_SLEEP_SECONDS = 20 * 60  # 20 minutes
GITHUB_NETLOCS = {"github.com", "www.github.com"}

# ---------- Utilities ----------
def log(msg: str) -> None:
    print(msg, file=sys.stderr)

def normalize_github_url(u: str) -> Optional[str]:
    if not isinstance(u, str) or not u.strip():
        return None
    try:
        p = urlparse(u.strip())
        if p.scheme not in {"http", "https"}: return None
        if p.netloc not in GITHUB_NETLOCS: return None
        return u.strip()
    except Exception:
        return None

def owner_repo_from_url(repo_url: str) -> Optional[Tuple[str, str]]:
    try:
        p = urlparse(repo_url)
        parts = [x for x in p.path.split("/") if x]
        if len(parts) < 2: return None
        owner, repo = parts[0], parts[1]
        if repo.endswith(".git"): repo = repo[:-4]
        return owner, repo
    except Exception:
        return None

def ext_of(path: str) -> str:
    return os.path.splitext(path)[1].lower()

def is_doc_file(path: str) -> bool:
    if not path: return False
    return os.path.basename(path).upper().startswith("README") or ext_of(path) in DOC_EXTS

def contains_keywords(text: str) -> Set[str]:
    found: Set[str] = set()
    if not isinstance(text, str): return found
    if re.search(r"(?i)test", text): found.add("test")
    if re.search(r"(?i)testing", text): found.add("testing")
    return found

def safe_api_call(fn, *args, **kwargs):
    while True:
        try:
            return fn(*args, **kwargs)
        except HTTPError as e:
            msg = str(e).lower()
            status = getattr(e, "status", None)
            if status == 403 and "rate limit" in msg and "exceeded" in msg:
                log("⚠️  GitHub API rate limit reached. Sleeping for 20 minutes...")
                time.sleep(RATE_LIMIT_SLEEP_SECONDS)
                continue
            raise

def get_default_branch(gh: GhApi, owner: str, repo: str) -> Optional[str]:
    try:
        repo_obj = safe_api_call(gh.repos.get, owner, repo)
        # works for AttrDict or dict
        return getattr(repo_obj, "default_branch", None) or (repo_obj.get("default_branch") if isinstance(repo_obj, dict) else None)
    except Exception as e:
        log(f"   (skip) failed to get default branch for {owner}/{repo}: {e}")
        return None

def list_tree_paths_depth_le_1(gh: GhApi, owner: str, repo: str, branch: str) -> List[Tuple[str, str]]:
    """
    Return (type, path) for 'blob' entries with depth <= 1 from default branch tree.
    """
    try:
        br = safe_api_call(gh.repos.get_branch, owner, repo, branch)
        # robustly extract SHA
        sha = None
        if isinstance(br, dict):
            sha = ((br.get("commit") or {}).get("sha"))
        else:
            commit = getattr(br, "commit", None)
            sha = getattr(commit, "sha", None)
        if not sha:
            log(f"   (skip) could not resolve commit sha for {owner}/{repo}@{branch}")
            return []

        # FIX: use tree_sha=sha (NOT sha=sha)
        tree = safe_api_call(gh.git.get_tree, owner, repo, tree_sha=sha, recursive=True)

        entries = None
        if isinstance(tree, dict):
            entries = tree.get("tree")
        else:
            entries = getattr(tree, "tree", None)
        if not entries:
            return []

        out: List[Tuple[str, str]] = []
        for it in entries:
            typ = it.get("type") if isinstance(it, dict) else getattr(it, "type", None)
            path = it.get("path") if isinstance(it, dict) else getattr(it, "path", None)
            if typ == "blob" and path and path.count("/") <= 1:
                out.append((typ, path))
        return out
    except HTTPError as e:
        if getattr(e, "status", None) == 404:
            log("   (skip) tree not found (404)")
            return []
        raise
    except Exception as e:
        log(f"   (skip) unexpected tree error: {e}")
        return []

def fetch_raw_text(owner: str, repo: str, branch: str, path: str) -> str:
    if not path: return ""
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    try:
        import urllib.request
        req = urllib.request.Request(url)
        token = os.getenv("GITHUB_TOKEN")
        if token: req.add_header("Authorization", f"token {token}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""

def scan_repo_for_keywords(gh: GhApi, owner: str, repo: str) -> Tuple[Set[str], List[str], List[str]]:
    found_total: Set[str] = set()
    hit_paths: List[str] = []
    scanned_paths: List[str] = []

    branch = get_default_branch(gh, owner, repo)
    if not branch:
        return found_total, hit_paths, scanned_paths

    entries = list_tree_paths_depth_le_1(gh, owner, repo, branch)
    if not entries:
        return found_total, hit_paths, scanned_paths

    doc_files = [p for (_t, p) in entries if is_doc_file(p)]

    for p in doc_files:
        scanned_paths.append(p)
        text = fetch_raw_text(owner, repo, branch, p)
        if not text:
            continue
        found = contains_keywords(text)
        if found:
            found_total |= found
            hit_paths.append(p)

    return found_total, hit_paths, scanned_paths

def main():
    parser = argparse.ArgumentParser(description="Filter repos and scan top-level docs for testing-related keywords.")
    parser.add_argument("input_csv", nargs="?", help="Path to input CSV")
    parser.add_argument("output_csv", nargs="?", help="Path to output CSV")
    parser.add_argument("-i", "--input", dest="input_opt", help="Path to input CSV")
    parser.add_argument("-o", "--output", dest="output_opt", help="Path to output CSV")
    parser.add_argument("-d", "--delimiter", default=",", help="CSV delimiter for input and output (default: ',')")
    args = parser.parse_args()

    in_csv = args.input_opt or args.input_csv
    out_csv = args.output_opt or args.output_csv
    if not in_csv or not out_csv:
        parser.error("Please provide INPUT and OUTPUT via positionals or -i/-o.")

    # Load
    try:
        df = pd.read_csv(in_csv, sep=args.delimiter, on_bad_lines="skip")
    except Exception as e:
        log(f"Failed to read input CSV: {e}")
        sys.exit(1)

    # Ensure result columns exist
    for col in ("test_keyword_found", "test_keyword_paths", "docs_scanned_paths"):
        if col not in df.columns:
            df[col] = ""

    # Required columns
    if "html_url" not in df.columns or "Language" not in df.columns:
        log("Input CSV must contain 'html_url' and 'Language' columns.")
        sys.exit(1)

    # Filter (GitHub URLs + desired languages)
    mask = df["html_url"].apply(lambda x: normalize_github_url(x) is not None) & \
           df["Language"].apply(lambda x: x in TARGET_LANGUAGES)
    filtered = df[mask].copy()

    if filtered.empty:
        log("ℹ️ No rows matched GitHub URL + target languages. Writing original CSV with empty results columns.")
        try:
            df.to_csv(out_csv, index=False, sep=args.delimiter, quoting=csv.QUOTE_MINIMAL)
        except Exception as e:
            log(f"Failed to write output CSV: {e}")
            sys.exit(1)
        return

    # Auth (.env three levels up from this script)
    script_dir = os.path.dirname(os.path.realpath(__file__))
    env_path = os.path.join(script_dir, "..", "..", "..", ".env")
    load_dotenv(dotenv_path=env_path, override=True)
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        log(f"⚠️ GITHUB_TOKEN not found at {env_path}. You may hit stricter rate limits.")
    gh = GhApi(token=token)

    # Process sequentially
    for idx, row in filtered.iterrows():
        repo_url = normalize_github_url(row["html_url"])
        if not repo_url:
            continue
        owner_repo = owner_repo_from_url(repo_url)
        if not owner_repo:
            log(f"Could not parse owner/repo from URL: {repo_url}. Skipping.")
            continue
        owner, repo = owner_repo

        try:
            log(f"➡️ Scanning {owner}/{repo} …")
            found_keywords, hit_paths, scanned_paths = scan_repo_for_keywords(gh, owner, repo)
            df.at[idx, "test_keyword_found"] = "|".join(sorted(found_keywords))
            df.at[idx, "test_keyword_paths"] = "|".join(hit_paths)
            df.at[idx, "docs_scanned_paths"] = "|".join(scanned_paths)
            log(f"✔️ {owner}/{repo}: found={sorted(found_keywords)} hits={len(hit_paths)} scanned={len(scanned_paths)}")
        except HTTPError as e:
            log(f"API error for {owner}/{repo}: {e}. Skipping.")
            continue
        except Exception as e:
            log(f"Unexpected error for {owner}/{repo}: {e}. Skipping.")
            continue

    # Save
    try:
        df.to_csv(out_csv, index=False, sep=args.delimiter, quoting=csv.QUOTE_MINIMAL)
        log(f"✅ Wrote results to {out_csv}")
    except Exception as e:
        log(f"Failed to write output CSV: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
