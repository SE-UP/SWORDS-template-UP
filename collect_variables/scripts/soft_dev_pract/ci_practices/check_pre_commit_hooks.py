"""
Checks GitHub repositories for the presence of a .pre-commit-config.yaml
file and logs results to a CSV.
Usage:
    python script.py --input input.csv --output output.csv
"""

import os
import time  # standard import first
import argparse
import pandas as pd
from github import Github, GithubException, RateLimitExceededException
from dotenv import load_dotenv

# Load .env file
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
ENV_PATH = os.path.join(SCRIPT_DIR, '..', '..', '..', '..', '.env')
load_dotenv(dotenv_path=ENV_PATH, override=True)


def check_ci_hook(html_url, github_instance):
    """
    Check if .pre-commit-config.yaml exists in the root of a GitHub repository.

    Args:
        html_url (str): The repository URL.
        github_instance (Github): Authenticated GitHub instance.

    Returns:
        str: 'Present', 'Not Present', 'Not Supported', or 'Error'.
    """
    try:
        if not html_url.startswith(("https://github.com", "http://github.com")):
            return "Not Supported"

        parts = html_url.rstrip('/').split('/')
        if len(parts) < 5:
            return "Error"

        owner, repo_name = parts[-2], parts[-1]
        repo = github_instance.get_repo(f"{owner}/{repo_name}")

        contents = repo.get_contents('/')
        for content in contents:
            if content.name == ".pre-commit-config.yaml":
                return "Present"
        return "Not Present"

    except RateLimitExceededException:
        print("Rate limit exceeded. Sleeping for 20 minutes...")
        time.sleep(20 * 60)
        return check_ci_hook(html_url, github_instance)
    except GithubException as exc:
        print(f"GitHub API error for {html_url}: {exc}")
        return "Error"
    except Exception as exc:
        print(f"General error for {html_url}: {exc}")
        return "Error"


def main(input_csv, output_csv):
    """
    Main logic to check repositories and save results.
    """
    token = os.getenv("GITHUB_TOKEN")
    username = os.getenv("GITHUB_USERNAME")

    if not token or not username:
        print("GitHub token or username not found in .env file.")
        return

    github_instance = Github(token)

    try:
        data = pd.read_csv(input_csv)
    except Exception as exc:
        print(f"Error reading input file: {exc}")
        return

    if "html_url" not in data.columns:
        print("Input file does not contain 'html_url' column.")
        return

    data["ci_hook"] = ""
    skipped_urls = []

    for index, row in data.iterrows():
        html_url = row["html_url"]
        print(f"Processing: {html_url}")

        try:
            result = check_ci_hook(html_url, github_instance)
            data.at[index, "ci_hook"] = result

            if result in ["Error", "Not Supported"]:
                skipped_urls.append(html_url)

        except Exception as exc:
            print(f"Error processing {html_url}: {exc}")
            skipped_urls.append(html_url)

    try:
        data.to_csv(output_csv, index=False)
        print(f"Results saved to {output_csv}")

        skipped_file = output_csv.replace(".csv", "_skipped_urls.txt")
        with open(skipped_file, "w", encoding="utf-8") as file:  # Specify encoding
            for url in skipped_urls:
                file.write(f"{url}\n")
        print(f"Skipped URLs saved to {skipped_file}")

    except Exception as exc:
        print(f"Error saving output file: {exc}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Check for .pre-commit-config.yaml in GitHub repositories."
    )
    parser.add_argument("--input", required=True, help="Path to input CSV file.")
    parser.add_argument("--output", required=True, help="Path to output CSV file.")

    args = parser.parse_args()
    main(args.input, args.output)

