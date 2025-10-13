"""
Scan GitHub repositories for CI YAML files and detect language-specific test rules.

Reads a CSV, filters repositories by valid GitHub URL, Language in {Python, R, C++},
and continuous_integration == True; inspects CI configuration for GitHub Actions,
Travis CI, CircleCI, Azure Pipelines (YAML) and records whether language-specific
test keywords appear in any .yml/.yaml files.

Outputs the original CSV plus:
- ci_tool_detected: comma-separated detected CI tools
- test_rule_in_ci: boolean, if any test keyword was found
- file_ci_test_rule_found: comma-separated YAML file paths where keywords were found
- test_keyword_found: comma-separated canonical keywords that matched

Usage:
    python add_ci_test_rule.py --input INPUT.csv --output OUTPUT.csv
"""

from __future__ import annotations

import argparse
import csv as _csv
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import pandas as pd
from dotenv import load_dotenv
from github import Github, GithubException, UnknownObjectException

# -----------------------------
# Constants / configuration
# -----------------------------

TARGET_LANGS = {"python", "r", "c++"}

# Canonical keyword -> regex (per language)
LANG_KEYWORDS: Dict[str, Dict[str, str]] = {
    "python": {
        "pytest": r"\bpytest\b",
        "unittest": r"\bunittest\b|\bunit\s*test\b",
        "nose": r"\bnose\b",
    },
    "r": {
        "testthat": r"\btestthat\b",
        "tinytest": r"\btinytest\b",
    },
    "c++": {
        "ctest": r"\bctest\b",
        "gtest": r"\bgtest\b|\bgoogle\s*test\b",
        "catch2": r"\bcatch2\b|\bcatch\s*2\b",
    },
}

# CI tool -> (detector paths, YAML patterns)
CI_PATTERNS: Dict[str, Dict[str, Sequence[str]]] = {
    "github_actions": {
        "detectors": (".github/workflows",),
        "yaml_globs": (".github/workflows/*.yml", ".github/workflows/*.yaml"),
    },
    "travis_ci": {
        "detectors": (".travis.yml", ".travis.yaml"),
        "yaml_globs": (".travis.yml", ".travis.yaml"),
    },
    "circle_ci": {
        "detectors": (".circleci",),
        "yaml_globs": (".circleci/config.yml", ".circleci/config.yaml"),
    },
    "azure_pipelines": {
        "detectors": ("azure-pipelines.yml", "azure-pipelines.yaml", "azure-pipelines"),
        "yaml_globs": (
            "azure-pipelines.yml",
            "azure-pipelines.yaml",
            "azure-pipelines/*.yml",
            "azure-pipelines/*.yaml",
        ),
    },
    # Jenkins is Groovy-based (not YAML); we only detect presence.
    "jenkins": {
        "detectors": ("Jenkinsfile", "jenkinsfile"),
        "yaml_globs": (),
    },
}

SLEEP_ON_RATE_LIMIT_SECONDS = 20 * 60  # 20 minutes


# -----------------------------
# Utilities
# -----------------------------

def setup_logging() -> None:
    """Configure console logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def load_token_from_env(script_path: Path) -> Optional[str]:
    """Load GITHUB_TOKEN from a .env relative to the script and/or environment.

    Args:
        script_path: Path to this script.

    Returns:
        The token string if available; otherwise None.
    """
    script_dir = script_path.resolve().parent
    env_path = os.path.join(script_dir, "..", "..", "..", "..", ".env")
    load_dotenv(dotenv_path=env_path, override=True)
    return os.getenv("GITHUB_TOKEN")


def normalize_repo_url(raw_url: object) -> Optional[str]:
    """Normalize a GitHub repository URL and ensure scheme/domain are valid.

    Accepts http, https, and 'www.'-prefixed inputs; trims to owner/repo.

    Args:
        raw_url: Value from the CSV 'html_url' column.

    Returns:
        Canonical https://github.com/OWNER/REPO or None if invalid.
    """
    if not isinstance(raw_url, str):
        return None
    url = raw_url.strip()
    if not url:
        return None
    if url.startswith("www."):
        url = "https://" + url
    parts = urlparse(url)
    if parts.scheme not in {"http", "https"}:
        return None
    if "github.com" not in parts.netloc.lower():
        return None
    path = parts.path.strip("/")
    if not path:
        return None
    path = re.sub(r"\.git$", "", path)
    owner_repo = path.split("/")
    if len(owner_repo) < 2:
        return None
    return f"https://github.com/{owner_repo[0]}/{owner_repo[1]}"


def owner_repo_from_url(url: str) -> Optional[Tuple[str, str]]:
    """Extract (owner, repo) from a canonical GitHub URL.

    Args:
        url: Canonical URL like https://github.com/OWNER/REPO

    Returns:
        Tuple (owner, repo) or None if parsing fails.
    """
    parts = urlparse(url)
    segs = parts.path.strip("/").split("/")
    if len(segs) < 2:
        return None
    return segs[0], segs[1]


def str_to_bool(val: object) -> bool:
    """Coerce common truthy/falsey values to bool.

    Args:
        val: Any input (bool/str/number).

    Returns:
        Boolean value; defaults to False if unknown.
    """
    if isinstance(val, bool):
        return val
    s_val = str(val).strip().lower()
    if s_val in {"true", "1", "yes", "y", "t"}:
        return True
    if s_val in {"false", "0", "no", "n", "f"}:
        return False
    return False


# -----------------------------
# Scanner
# -----------------------------

@dataclass
class RepoScanner:
    """Scanner for CI YAMLs and test keyword detection in GitHub repos."""
    gh: Github
    sleep_on_limit: int = SLEEP_ON_RATE_LIMIT_SECONDS

    def ensure_rate_limit(self) -> None:
        """Sleep when core rate limit is exhausted; brief pause when very low."""
        try:
            rl = self.gh.get_rate_limit()
            remaining = rl.core.remaining
            reset_ts = rl.core.reset.timestamp()
            now = time.time()
            if remaining <= 0:
                sleep_for = max(self.sleep_on_limit, int(reset_ts - now) + 5)
                logging.warning(
                    "Rate limit reached. Sleeping for %d sec...", sleep_for
                )
                time.sleep(sleep_for)
            elif remaining < 10 and reset_ts > now:
                pause = int(min(60, reset_ts - now))
                logging.info("Rate low (%d). Sleeping %d sec...", remaining, pause)
                time.sleep(pause)
        except Exception as exc:  # pylint: disable=broad-except
            logging.debug("Rate limit check failed: %s", exc)

    def list_dir(self, repo, path: str) -> List:
        """List directory contents or return empty list if missing."""
        self.ensure_rate_limit()
        try:
            items = repo.get_contents(path)
            return items if isinstance(items, list) else [items]
        except UnknownObjectException:
            return []
        except GithubException as exc:
            logging.debug("list_dir error %s:%s -> %s", repo.full_name, path, exc)
            return []

    def read_file_text(self, repo, path: str) -> Optional[str]:
        """Read file text content; return None if not found or on API error."""
        self.ensure_rate_limit()
        try:
            obj = repo.get_contents(path)
            return obj.decoded_content.decode("utf-8", errors="replace")
        except UnknownObjectException:
            return None
        except GithubException as exc:
            logging.debug("read_file_text error %s:%s -> %s", repo.full_name, path, exc)
            return None

    def glob_yaml_candidates(self, repo, patterns: Iterable[str]) -> List[str]:
        """Resolve simple YAML globs like 'dir/*.yml' within the repo.

        Args:
            repo: PyGithub Repository object.
            patterns: Iterable of patterns.

        Returns:
            List of matched file paths (deduplicated, order preserved).
        """
        matches: List[str] = []
        for patt in patterns:
            if "*" not in patt:
                if self.read_file_text(repo, patt) is not None:
                    matches.append(patt)
                continue
            # Support "dir/*.ext" form
            match = re.match(r"^(?P<dir>[^*]+)/\*(?P<ext>\.[^.]+)$", patt)
            if not match:
                continue
            dir_name = match.group("dir")
            ext = match.group("ext").lower()
            for item in self.list_dir(repo, dir_name):
                if getattr(item, "type", "") == "file" and item.path.lower().endswith(ext):
                    matches.append(item.path)
        # de-dup preserve order
        seen: set[str] = set()
        unique: List[str] = []
        for path in matches:
            if path not in seen:
                seen.add(path)
                unique.append(path)
        return unique

    def detect_ci_yaml_files(self, repo) -> Dict[str, List[str]]:
        """Detect CI tools and collect YAML files to scan.

        Args:
            repo: PyGithub Repository.

        Returns:
            Mapping of ci_tool -> list of YAML file paths (may be empty for Jenkins).
        """
        found: Dict[str, List[str]] = {}
        for tool, cfg in CI_PATTERNS.items():
            detected = False
            for d_path in cfg["detectors"]:
                # file or directory presence
                if self.read_file_text(repo, d_path) is not None or self.list_dir(repo, d_path):
                    detected = True
                    break
            if not detected:
                continue
            yaml_files = self.glob_yaml_candidates(repo, cfg["yaml_globs"]) if cfg["yaml_globs"] else []
            found[tool] = yaml_files
        return found

    @staticmethod
    def search_keywords_in_files(
        repo_reader: "RepoScanner",
        repo,
        files: Sequence[str],
        keyword_map: Dict[str, str],
    ) -> Tuple[bool, List[str], List[str]]:
        """Search keyword regexes in provided YAML files.

        Args:
            repo_reader: The RepoScanner (for read_file_text).
            repo: PyGithub Repository.
            files: YAML candidate file paths.
            keyword_map: Canonical keyword -> regex.

        Returns:
            (found_any, matching_files, matched_keywords)
        """
        compiled = [(name, re.compile(rx, re.IGNORECASE)) for name, rx in keyword_map.items()]
        matched_files: List[str] = []
        matched_keywords: List[str] = []
        seen_keywords: set[str] = set()

        for path in files:
            text = repo_reader.read_file_text(repo, path)
            if text is None:
                continue
            file_has_match = False
            for name, creg in compiled:
                if creg.search(text):
                    if name not in seen_keywords:
                        seen_keywords.add(name)
                        matched_keywords.append(name)
                    file_has_match = True
            if file_has_match:
                matched_files.append(path)

        return bool(matched_files), matched_files, matched_keywords


# -----------------------------
# Core pipeline
# -----------------------------

def process_csv(input_csv: Path, output_csv: Path) -> None:
    """Process the CSV, scan matching repos, and write augmented CSV.

    Args:
        input_csv: Path to the input CSV file.
        output_csv: Path to write the augmented CSV.

    Returns:
        None. Writes the output CSV to `output_csv`.
    """
    # Read & preserve all data
    df = pd.read_csv(input_csv, engine="python", quoting=_csv.QUOTE_MINIMAL)

    # Required columns
    for col in ("html_url", "Language", "continuous_integration"):
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    # Prepare output columns without losing any existing data
    for col in ("ci_tool_detected", "test_rule_in_ci", "file_ci_test_rule_found", "test_keyword_found"):
        if col not in df.columns:
            df[col] = pd.NA

    # Auth
    token = load_token_from_env(Path(__file__))
    if token:
        gh = Github(token)
    else:
        logging.warning("GITHUB_TOKEN not found; continuing anonymously (very limited rate).")
        gh = Github()

    scanner = RepoScanner(gh=gh)

    processed = 0
    for idx, row in df.iterrows():
        raw_url = row.get("html_url")
        language = str(row.get("Language") or "").strip()
        has_ci = str_to_bool(row.get("continuous_integration"))

        canonical = normalize_repo_url(raw_url)
        if not canonical:
            logging.info("[skip] idx=%s invalid html_url=%r", idx, raw_url)
            continue

        if language.lower() not in TARGET_LANGS:
            continue

        if not has_ci:
            continue

        owner_repo = owner_repo_from_url(canonical)
        if not owner_repo:
            logging.info("[skip] idx=%s cannot parse owner/repo from %r", idx, raw_url)
            continue
        owner, repo_name = owner_repo

        scanner.ensure_rate_limit()
        try:
            repo = gh.get_repo(f"{owner}/{repo_name}")
        except GithubException as exc:
            logging.info("[skip] idx=%s cannot access %s/%s: %s", idx, owner, repo_name, exc)
            continue

        logging.info("[proc] idx=%s %s/%s (Language=%s)", idx, owner, repo_name, language)

        ci_to_files = scanner.detect_ci_yaml_files(repo)
        detected_tools = list(ci_to_files.keys())
        yaml_candidates: List[str] = []
        for files in ci_to_files.values():
            yaml_candidates.extend(files)
        # de-dup while preserving order
        yaml_candidates = list(dict.fromkeys(yaml_candidates))

        lang_key = language.lower()
        keyword_map = LANG_KEYWORDS.get(lang_key, {})

        found = False
        found_files: List[str] = []
        matched_keywords: List[str] = []
        if yaml_candidates and keyword_map:
            found, found_files, matched_keywords = RepoScanner.search_keywords_in_files(
                scanner, repo, yaml_candidates, keyword_map
            )

        # Record results
        df.at[idx, "ci_tool_detected"] = ",".join(detected_tools) if detected_tools else pd.NA
        df.at[idx, "test_rule_in_ci"] = bool(found) if detected_tools else False
        df.at[idx, "file_ci_test_rule_found"] = ",".join(found_files) if found_files else (pd.NA if detected_tools else pd.NA)
        df.at[idx, "test_keyword_found"] = ",".join(matched_keywords) if matched_keywords else (pd.NA if detected_tools else pd.NA)

        processed += 1
        if processed % 10 == 0:
            logging.info("Processed %d repositories...", processed)

    # Write output file
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)
    logging.info("Done. Wrote: %s (processed %d repos).", output_csv, processed)


# -----------------------------
# CLI
# -----------------------------

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Optional sequence of CLI args (for testing). Defaults to sys.argv.

    Returns:
        argparse.Namespace with `input` and `output` attributes.
    """
    parser = argparse.ArgumentParser(
        description="Scan CI YAMLs in GitHub repos for language-specific test rules."
    )
    parser.add_argument("--input", required=True, type=Path, help="Input CSV file path")
    parser.add_argument("--output", required=True, type=Path, help="Output CSV file path")
    return parser.parse_args(argv)


def main() -> None:
    """Entry point."""
    setup_logging()
    args = parse_args()
    try:
        process_csv(args.input, args.output)
    except Exception as exc:  # pylint: disable=broad-except
        logging.exception("Fatal error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
