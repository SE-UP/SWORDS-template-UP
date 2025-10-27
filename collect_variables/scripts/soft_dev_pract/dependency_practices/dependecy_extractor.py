"""
Check language-specific dependency/spec files for Python, R, and C/C++ repositories.
Searches repo root and immediate subfolders (one level deep).
Extracts dependency names into 'dependecies_found' and flags presence in 'requirements_defined'.

Usage:
    python dependency_lock_files.py --input <input_csv_file> --output <output_csv_file>
"""

import argparse
import os
import time
import json
import re
import logging
import pandas as pd
from dotenv import load_dotenv
from github import Github, GithubException, RateLimitExceededException

# ---------- Setup ----------
script_dir = os.path.dirname(os.path.realpath(__file__))
env_path = os.path.join(script_dir, "..", "..", "..", "..", ".env")
load_dotenv(dotenv_path=env_path, override=True)

token = os.getenv("GITHUB_TOKEN")
g = Github(token)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

# ---------- Parsers ----------

def parse_requirements_txt(text):
    """
    Parse pip requirements/constraints-like files.
    - Ignores comments/options/VCS/editables
    - Handles '-r other.txt' includes (the caller handles reading includes)
    Returns (deps, includes)
    """
    deps = []
    includes = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-e ", "git+", "hg+", "svn+", "bzr+")):
            continue
        if line.startswith(("--", "-c", "-f ", "--find-links", "--extra-index-url", "--index-url", "--trusted-host")):
            continue
        if line.startswith("-r "):
            inc = line[3:].strip()
            if inc:
                includes.append(inc)
            continue
        token = re.split(r"[ ;]", line, 1)[0]
        name = re.split(r"(==|>=|<=|~=|!=|>|<)", token)[0].strip()
        if name:
            deps.append(name)
    return sorted(set(deps)), includes

def parse_pipfile_lock(text):
    try:
        data = json.loads(text)
        deps = set()
        for section in ("default", "develop"):
            deps.update((data.get(section) or {}).keys())
        return sorted(deps)
    except Exception:
        return []

def parse_poetry_lock(text):
    deps = []
    in_pkg = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[[package]]"):
            in_pkg = True
            continue
        if in_pkg and line.startswith("[["):
            in_pkg = False
        if in_pkg and line.startswith('name ='):
            m = re.search(r'name\s*=\s*"([^"]+)"', line)
            if m:
                deps.append(m.group(1))
    return sorted(set(deps))

def parse_uv_lock(text):
    # uv.lock is TOML-like; reuse poetry parser heuristics
    return parse_poetry_lock(text)

def parse_pyproject_toml(text):
    """
    Lightweight extraction for:
    - [project] dependencies = ["a", "b>=1"]
    - [project.optional-dependencies.<extra>] = [...]
    - [tool.poetry.dependencies] and related sections (best-effort)
    Heuristic only (no TOML parser).
    """
    deps = set()

    # [project] dependencies = [ ... ]
    for m in re.finditer(r'^\s*dependencies\s*=\s*\[(.*?)\]', text, re.M | re.S):
        arr = m.group(1)
        for s in re.findall(r'"([^"]+)"|\'([^\']+)\'', arr):
            item = (s[0] or s[1]).strip()
            if item:
                name = re.split(r"(==|>=|<=|~=|!=|>|<)", re.split(r"[ ;]", item)[0])[0]
                deps.add(name)

    # [project.optional-dependencies.*]
    for block in re.finditer(r'^\s*\[project\.optional-dependencies[^\]]*\]\s*(.*?)\n(?=\[|$)', text, re.M | re.S):
        body = block.group(1)
        for m in re.finditer(r'=\s*\[(.*?)\]', body, re.S):
            arr = m.group(1)
            for s in re.findall(r'"([^"]+)"|\'([^\']+)\'', arr):
                item = (s[0] or s[1]).strip()
                if item:
                    name = re.split(r"(==|>=|<=|~=|!=|>|<)", re.split(r"[ ;]", item)[0])[0]
                    deps.add(name)

    # [tool.poetry.*] (best-effort key extraction)
    for section in re.finditer(r'^\s*\[tool\.poetry(\.[^\]]+)?\]\s*(.*?)\n(?=\[|$)', text, re.M | re.S):
        body = section.group(2)
        in_deps_table = False
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "[")):
                continue
            m = re.match(r'([A-Za-z0-9_.\-]+)\s*=\s*(.+)', line)
            if not m:
                continue
            key, _val = m.group(1), m.group(2)
            if key in {"name", "version", "description", "authors"}:
                continue
            deps.add(key)

    return sorted(deps)

def parse_renv_lock(text):
    try:
        data = json.loads(text)
        return sorted((data.get("Packages") or {}).keys())
    except Exception:
        return []

def parse_r_description(text):
    """
    Parse DESCRIPTION fields: Depends, Imports, Suggests, LinkingTo.
    """
    deps = set()
    fields = {}
    key = None
    for raw in text.splitlines():
        if re.match(r'^[A-Za-z][A-Za-z0-9-]*\s*:', raw):
            key, val = raw.split(":", 1)
            fields[key.strip()] = val.strip()
        elif key and raw.startswith((" ", "\t")):
            fields[key] += " " + raw.strip()
        else:
            key = None
    for k in ("Depends", "Imports", "Suggests", "LinkingTo"):
        v = fields.get(k)
        if not v:
            continue
        for part in v.split(","):
            name = part.strip()
            if name:
                name = re.sub(r"\s*\(.*?\)", "", name).strip()
                if name and name.lower() != "r":
                    deps.add(name)
    return sorted(deps)

def parse_vcpkg_json(text):
    try:
        data = json.loads(text)
        deps = set()
        val = data.get("dependencies")
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    deps.add(item)
                elif isinstance(item, dict):
                    name = item.get("name")
                    if name:
                        deps.add(name)
        # features may declare extra deps
        feats = data.get("features")
        if isinstance(feats, dict):
            for feat in feats.values():
                if isinstance(feat, dict):
                    fdeps = feat.get("dependencies", [])
                    for item in fdeps:
                        if isinstance(item, str):
                            deps.add(item)
                        elif isinstance(item, dict):
                            name = item.get("name")
                            if name:
                                deps.add(name)
        return sorted(deps)
    except Exception:
        return []

def parse_cmakelists(text):
    """
    Heuristic: find_package(), target_link_libraries(), add_subdirectory().
    """
    deps = set()
    for m in re.finditer(r'find_package\(\s*([A-Za-z0-9_+-]+)', text, re.I):
        deps.add(m.group(1))
    for m in re.finditer(r'target_link_libraries\([^)]*\)', text, re.I | re.S):
        content = m.group(0)
        for lib in re.findall(r'([A-Za-z0-9_+.-]+)::[A-Za-z0-9_+.-]+', content):
            deps.add(lib)
        for lib in re.findall(r'\s([A-Za-z0-9_+.-]+)\s', content):
            if lib.lower() not in {"private", "public", "interface", "optimized", "debug"}:
                if not lib.endswith((")", "(")):
                    deps.add(lib)
    for m in re.finditer(r'add_subdirectory\(\s*([^)]+)\)', text, re.I):
        path = m.group(1).strip().strip('"\'')
        leaf = path.rsplit("/", 1)[-1]
        if leaf:
            deps.add(leaf)
    return sorted(deps)

def parse_makefile(text):
    """
    Heuristic: libraries from pkg-config and -l flags.
    """
    deps = set()
    for m in re.finditer(r'pkg-config\s+--libs\s+([A-Za-z0-9_.+-]+)', text):
        deps.add(m.group(1))
    for m in re.finditer(r'\-l([A-Za-z0-9_.+-]+)', text):
        deps.add(m.group(1))
    return sorted(deps)

# ---------- File sets by language ----------

PYTHON_FILES = [
    "pyproject.toml",
    "Pipfile.lock",
    "poetry.lock",
    "uv.lock",
    # requirements*.txt handled via probing
]

R_FILES = [
    "DESCRIPTION",
    "renv.lock",
]

CPP_FILES = [
    "CMakeLists.txt",
    "Makefile",
    "vcpkg.json",
    # *.make handled via probing
]

# ---------- Helpers ----------

def is_github_url(url):
    return isinstance(url, str) and url.startswith("https://github.com/")

def get_repo(owner_repo):
    while True:
        try:
            return g.get_repo(owner_repo)
        except RateLimitExceededException:
            logging.warning("GitHub API rate limit exceeded. Sleeping for 15 minutes...")
            time.sleep(15 * 60)
        except GithubException as err:
            logging.error(f"Failed to access repo {owner_repo}: {str(err)}")
            return None

def try_get_file(repository, path):
    try:
        return repository.get_contents(path)
    except GithubException:
        return None

def try_get_file_text(repository, path):
    file = try_get_file(repository, path)
    if file is None:
        return None
    try:
        return file.decoded_content.decode("utf-8", errors="replace")
    except Exception:
        return None

# NEW: list root and immediate subdirectories (one level deep)
def get_root_and_one_level_dirs(repository):
    """
    Returns a list of base paths to search:
    - "" for root
    - "<subdir>" for each immediate child directory of the root
    """
    bases = [""]
    try:
        root_items = repository.get_contents("")  # list root
        for item in root_items:
            if getattr(item, "type", "") == "dir":
                bases.append(item.path)  # e.g., "src", "dependencies", "env"
    except RateLimitExceededException:
        logging.warning("Rate limit while listing root. Sleeping for 15 minutes...")
        time.sleep(15 * 60)
        return get_root_and_one_level_dirs(repository)
    except GithubException as err:
        logging.error(f"Could not list root directory: {err}")
    return bases

def list_paths_like(repository, base, patterns):
    """
    Try exact filenames plus simple 'glob' probes:
    - requirements*.txt
    - *.make
    Returns existing paths.
    """
    found = []
    prefix = f"{base}/" if base else ""
    # exact names
    for name in patterns.get("exact", []):
        path = f"{prefix}{name}"
        if try_get_file(repository, path):
            found.append(path)
    # requirements*.txt
    if patterns.get("requirements_glob"):
        for cand in (
            "requirements.txt",
            "requirements-dev.txt",
            "requirements_test.txt",
            "requirements-ci.txt",
            "requirements_prod.txt",
            "constraints.txt",
        ):
            path = f"{prefix}{cand}"
            if try_get_file(repository, path):
                found.append(path)
    # *.make
    if patterns.get("make_glob"):
        for cand in ("build.make", "rules.make", "deps.make", "custom.make"):
            path = f"{prefix}{cand}"
            if try_get_file(repository, path):
                found.append(path)
    return sorted(set(found))

def collect_for_language(repository, language):
    """
    Search root and one-level subdirs for language-specific files.
    Return (found_any, deps, found_files)
    """
    lang = (language or "").lower()
    if lang == "python":
        bucket = "python"
    elif lang == "r":
        bucket = "r"
    elif lang in ("c++", "c", "objective-c++"):
        bucket = "cpp"
    else:
        return False, [], []

    candidate_dirs = get_root_and_one_level_dirs(repository)

    all_deps = set()
    found_files = []
    found_any = False

    for base in candidate_dirs:
        if bucket == "python":
            patterns = {"exact": PYTHON_FILES, "requirements_glob": True, "make_glob": False}
            paths = list_paths_like(repository, base, patterns)
            for path in paths:
                text = try_get_file_text(repository, path)
                if text is None:
                    continue
                found_any = True
                found_files.append(path)
                fname = path.rsplit("/", 1)[-1].lower()
                if fname == "pyproject.toml":
                    all_deps.update(parse_pyproject_toml(text))
                elif fname == "pipfile.lock":
                    all_deps.update(parse_pipfile_lock(text))
                elif fname == "poetry.lock":
                    all_deps.update(parse_poetry_lock(text))
                elif fname == "uv.lock":
                    all_deps.update(parse_uv_lock(text))
                elif fname.endswith(".txt") and fname.startswith("requirements"):
                    deps, includes = parse_requirements_txt(text)
                    all_deps.update(deps)
                    # follow simple includes relative to this base
                    for inc in includes:
                        inc_path = f"{base}/{inc}" if base else inc
                        inc_text = try_get_file_text(repository, inc_path)
                        if inc_text:
                            inc_deps, _ = parse_requirements_txt(inc_text)
                            all_deps.update(inc_deps)
                            found_files.append(inc_path)

        elif bucket == "r":
            patterns = {"exact": R_FILES, "requirements_glob": False, "make_glob": False}
            paths = list_paths_like(repository, base, patterns)
            for path in paths:
                text = try_get_file_text(repository, path)
                if text is None:
                    continue
                found_any = True
                found_files.append(path)
                if path.endswith("DESCRIPTION"):
                    all_deps.update(parse_r_description(text))
                elif path.endswith("renv.lock"):
                    all_deps.update(parse_renv_lock(text))

        elif bucket == "cpp":
            patterns = {"exact": CPP_FILES, "requirements_glob": False, "make_glob": True}
            paths = list_paths_like(repository, base, patterns)
            for path in paths:
                text = try_get_file_text(repository, path)
                if text is None:
                    continue
                found_any = True
                found_files.append(path)
                fname = path.rsplit("/", 1)[-1].lower()
                if fname == "cmakelists.txt":
                    all_deps.update(parse_cmakelists(text))
                elif fname == "makefile" or fname.endswith(".make"):
                    all_deps.update(parse_makefile(text))
                elif fname == "vcpkg.json":
                    all_deps.update(parse_vcpkg_json(text))

    if found_files:
        logging.info(f"Found language-specific files ({language}): {found_files}")

    return found_any, sorted(all_deps), found_files

def check_requirements_and_dependencies(repository_url):
    """
    1) Detect dominant language via GH API.
    2) Search & parse files only for that language bucket.
    """
    url_parts = repository_url.rstrip("/").split("/")
    if len(url_parts) < 2:
        return None, []
    owner = url_parts[-2]
    repo = url_parts[-1]

    repository = get_repo(f"{owner}/{repo}")
    if repository is None:
        return None, []

    language = repository.language  # dominant language
    found_any, deps, _files = collect_for_language(repository, language)
    return found_any, deps

# ---------- Main ----------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Detect language-specific dependency/spec files in GitHub repositories from a CSV and extract dependency names. Searches repo root and immediate subfolders."
    )
    parser.add_argument(
        "--input",
        type=str,
        default="../collect_repositories/results/repositories_filtered.csv",
        help="Input CSV file containing GitHub repository URLs (expects a column 'html_url')",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="results/soft_dev_pract.csv",
        help="Output CSV file to save results",
    )
    args = parser.parse_args()

    # Read input (semicolon delimiter as per your original)
    try:
        df = pd.read_csv(args.input, delimiter=",", encoding="utf-8")
    except UnicodeDecodeError:
        logging.warning(
            f"Error reading {args.input} with UTF-8 encoding. Trying ISO-8859-1..."
        )
        df = pd.read_csv(args.input, delimiter=";", encoding="ISO-8859-1")

    if "requirements_defined" not in df.columns:
        df["requirements_defined"] = None
    if "dependecies_found" not in df.columns:
        df["dependecies_found"] = None

    for idx, row in df.iterrows():
        repo_url = row.get("html_url")
        if not is_github_url(repo_url):
            logging.info(f"SKIP (invalid URL): {repo_url}")
            df.at[idx, "requirements_defined"] = None
            df.at[idx, "dependecies_found"] = None
            continue

        logging.info(f"PROCESS: {repo_url}")
        try:
            req_defined, deps = check_requirements_and_dependencies(repo_url)
            logging.info(
                f"RESULT: {repo_url} requirements_defined={req_defined} deps_count={len(deps)}"
            )
            df.at[idx, "requirements_defined"] = bool(req_defined)
            df.at[idx, "dependecies_found"] = json.dumps(deps, ensure_ascii=False)
        except RateLimitExceededException:
            logging.warning("Rate limit hit during processing. Sleeping for 15 minutes...")
            time.sleep(15 * 60)
            req_defined, deps = check_requirements_and_dependencies(repo_url)
            logging.info(
                f"RESULT (after sleep): {repo_url} requirements_defined={req_defined} deps_count={len(deps)}"
            )
            df.at[idx, "requirements_defined"] = bool(req_defined)
            df.at[idx, "dependecies_found"] = json.dumps(deps, ensure_ascii=False)
        except Exception as err:
            logging.error(f"FAIL: {repo_url} error={err}")
            df.at[idx, "requirements_defined"] = None
            df.at[idx, "dependecies_found"] = None

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    df.to_csv(args.output, index=False)
    logging.info(f"Saved results to {args.output}")
