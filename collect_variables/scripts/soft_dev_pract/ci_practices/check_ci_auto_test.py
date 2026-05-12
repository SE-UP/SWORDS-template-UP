import argparse
import os
import time
import re
import pandas as pd
from github import Github, GithubException
from dotenv import load_dotenv
from urllib.parse import urlparse
from typing import Optional, List, Dict

# --- CONFIGURATION ---
LANG_KEYWORDS: Dict[str, Dict[str, str]] = {
    "python": {"pytest": r"\bpytest\b"},
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
# Finds the script's directory and looks 4 levels up for the .env file
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
ENV_PATH = os.path.join(SCRIPT_DIR, "..", "..", "..", "..", ".env")

def _parse_github_owner_repo(html_url: str) -> Optional[str]:
    if not html_url or pd.isna(html_url): return None
    url = str(html_url).strip()
    if url.startswith("github.com/"): url = "https://" + url
    parsed = urlparse(url)
    parts = [p for p in (parsed.path or "").split("/") if p]
    if len(parts) < 2: return None
    return f"{parts[0]}/{parts[1]}".replace(".git", "")

def get_file_content_safely(repo, path: str) -> str:
    try:
        content = repo.get_contents(path)
        return content.decoded_content.decode("utf-8")
    except:
        return ""

def walk_and_find_keywords(repo, path: str) -> str:
    combined_content = ""
    try:
        items = repo.get_contents(path)
        if not isinstance(items, list):
            if items.name.lower().endswith(('.yml', '.yaml')):
                return get_file_content_safely(repo, items.path)
            return ""
        for item in items:
            if item.type == "dir":
                combined_content += walk_and_find_keywords(repo, item.path)
            elif item.type == "file":
                if item.name.lower().endswith(('.yml', '.yaml')):
                    combined_content += get_file_content_safely(repo, item.path)
    except:
        pass
    return combined_content

def analyze_repo(g, owner_repo):
    # 1. Update dictionary values to be LISTS of strings
    ci_paths = {
        "github_actions": [".github"],
        "travis": [".travis.yml", ".travis.yaml"],
        "circleci": [".circleci"],
        "jenkins": ["Jenkinsfile"],
        "azure_pipelines": ["azure-pipelines.yml", "azure-pipelines.yaml"]
    }
    
    found_tools = []
    all_configs_text = ""
    repo = g.get_repo(owner_repo)

    # 2. Iterate through the dictionary items
    for tool, paths in ci_paths.items():
        # 3. Add this nested loop to handle the "OR" logic
        for path in paths:
            try:
                repo.get_contents(path)
                found_tools.append(tool)
                
                # If the file/dir exists, scrape the text and STOP checking alternatives
                all_configs_text += walk_and_find_keywords(repo, path)
                break 
            except:
                # If the specific path is not found, try the next one in the list
                continue

    detected_frameworks = []
    for lang, frameworks in LANG_KEYWORDS.items():
        for fw_name, pattern in frameworks.items():
            if re.search(pattern, all_configs_text, re.IGNORECASE):
                detected_frameworks.append(fw_name)
                
    return found_tools, detected_frameworks

def main():
    # 1. SET UP COMMAND LINE ARGUMENTS for CSVs
    parser = argparse.ArgumentParser(description='GitHub CI/CD and Test Framework Analyzer')
    parser.add_argument('-i', '--input', required=True, help='Path to the input CSV file')
    parser.add_argument('-o', '--output', required=True, help='Path to save the output CSV file')
    args = parser.parse_args()

    # 2. INITIALIZE GITHUB API (Using your specific ENV_PATH)
    print(f"Searching for .env at: {os.path.abspath(ENV_PATH)}")
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    token = os.getenv('GITHUB_TOKEN')
    
    if not token:
        print(f"Error: GITHUB_TOKEN not found in .env at {ENV_PATH}")
        return
    
    g = Github(token)

    # 3. PROCESS DATA
    try:
        df = pd.read_csv(args.input, encoding='latin1')
    except Exception as e:
        print(f"Error reading input file: {e}")
        return

    # Ensure columns exist
    for col in ['continuous_integration', 'ci_tool', 'frameworks_detected']:
        if col not in df.columns: df[col] = ""

    print(f"Starting analysis on {len(df)} records...")

    for index, row in df.iterrows():
        owner_repo = _parse_github_owner_repo(row['html_url'])
        if not owner_repo: continue

        try:
            tools, frameworks = analyze_repo(g, owner_repo)
            df.at[index, 'continuous_integration'] = len(tools) > 0
            df.at[index, 'ci_tool'] = ", ".join(tools)
            df.at[index, 'frameworks_detected'] = ", ".join(frameworks)
            print(f"[SUCCESS] {owner_repo}: {len(tools)} tools, {len(frameworks)} frameworks.")
            
            # Save incrementally
            df.to_csv(args.output, index=False, encoding='latin1')

        except GithubException as e:
            if e.status == 403:
                print("Rate limit exceeded. Sleeping for 20 minutes...")
                time.sleep(1200)
            else:
                print(f"[ERROR] {owner_repo}: {e.data.get('message', 'Unknown error')}")
            continue

    print(f"Done! Results saved to {args.output}")

if __name__ == "__main__":
    main()