"""
Retrives dependecy .lock files for Python, R, C++

Usage: navigate to collect_variables and run:
python dependency_lock_files.py 
--input <input_csv_file> --output <output_csv_file>
"""

import argparse
import os
import time
import pandas as pd
from dotenv import load_dotenv
from github import Github, GithubException, RateLimitExceededException

script_dir = os.path.dirname(os.path.realpath(__file__))
env_path = os.path.join(script_dir, "..", "..", "..", "..", ".env")
load_dotenv(dotenv_path=env_path, override=True)

token = os.getenv("GITHUB_TOKEN")
g = Github(token)


def check_requirements(repository_url):
    """
    Check if requirements are made explicit in a GitHub repository.

    Args:
        repository_url (str): The GitHub repository URL.

    Returns:
        bool: True if requirements are found and explicit, False otherwise.
    """
    url_parts = repository_url.rstrip("/").split("/")
    owner = url_parts[-2]
    repo = url_parts[-1]

    try:
        repository = g.get_repo(f"{owner}/{repo}")
        repository_language = repository.language
        common_dependency_files = {
            "Python": ["Pipfile.lock", "poetry.lock", "requirement.lock"],
            "R": ["renv.lock", "packrat.lock"],
            "C++": ["vcpkg.lock", "conan.lock", "CMakeCache.txt"],
        }

        if repository_language in common_dependency_files:
            for dependency_file in common_dependency_files[repository_language]:
                try:
                    repository.get_contents(dependency_file)
                    return True
                except GithubException:
                    continue
        return False

    except RateLimitExceededException:
        print("GitHub API rate limit exceeded. Sleeping for 15 minutes...")
        time.sleep(15 * 60)
        return check_requirements(repository_url)

    except GithubException as err:
        print(f"Failed to check requirements for {repository_url}: {str(err)}")
        return None


def is_github_url(url):
    """
    Check if a URL is a valid GitHub URL.

    Args:
        url (str or None): The URL to check.

    Returns:
        bool: True if the URL is a valid GitHub repository URL, False otherwise.
    """
    if isinstance(url, str):
        return url.startswith("https://github.com/")
    return False


if __name__ == "__main__":
    argument_parser = argparse.ArgumentParser(
        description="Check requirements of GitHub repositories listed in a CSV file."
    )
    argument_parser.add_argument(
        "--input",
        type=str,
        default="../collect_repositories/results/repositories_filtered.csv",
        help="Input CSV file containing GitHub repository URLs",
    )
    argument_parser.add_argument(
        "--output",
        type=str,
        default="results/soft_dev_pract.csv",
        help="Output CSV file to save results",
    )
    command_line_arguments = argument_parser.parse_args()

    try:
        input_data = pd.read_csv(
            command_line_arguments.input, delimiter=";", encoding="utf-8"
        )
    except UnicodeDecodeError:
        print(
            f"Error reading {command_line_arguments.input} with UTF-8 encoding. "
            "Trying ISO-8859-1..."
        )
        input_data = pd.read_csv(
            command_line_arguments.input, delimiter=";", encoding="ISO-8859-1"
        )

    input_data["dependency_lock_files"] = ""

    for index, row in input_data.iterrows():
        repo_url = row["html_url"]

        if not is_github_url(repo_url):
            print(f"Skipping invalid or non-GitHub URL: {repo_url}")
            input_data.at[index, "dependency_lock_files"] = None
            continue

        result = check_requirements(repo_url)
        input_data.at[index, "requirements_defined"] = result

    input_data.to_csv(command_line_arguments.output, index=False)
    print(f"Results saved to {command_line_arguments.output}")
