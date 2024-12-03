"""
This script utilizes the GitHub API to retrieve repository details
and specific files (like requirements.txt, DESCRIPTION, CMakeLists.txt)
that typically document project dependencies. It handles GitHub API rate
limits by sleeping for 15 minutes if the limit is reached.
"""

import argparse
import os
import time
import pandas as pd
from dotenv import load_dotenv
from github import Github, GithubException, RateLimitExceededException

# Get the directory of the current script
script_dir = os.path.dirname(os.path.realpath(__file__))

# Create the relative path to the .env file
env_path = os.path.join(script_dir, '..', '..', '..','..', '.env')

# Load the .env file
load_dotenv(dotenv_path=env_path, override=True)

# Get the GITHUB_TOKEN from the .env file
token = os.getenv('GITHUB_TOKEN')

# Use the token to create a Github instance
g = Github(token)

def check_requirements(repository_url):
    """
    Check if requirements are made explicit in a GitHub repository.

    Args:
    - repository_url (str): The GitHub repository URL.

    Returns:
    - bool: True if requirements are found and explicit, False otherwise.
    """
    # Parse owner and repo from URL
    url_parts = repository_url.rstrip('/').split('/')
    owner = url_parts[-2]
    repo = url_parts[-1]

    try:
        # Get repository details
        repository = g.get_repo(f"{owner}/{repo}")

        # Get the programming language of the repository
        repository_language = repository.language

        # Define the common dependency files
        common_dependency_files = {
            'Python': ['requirements.txt', 'Pipfile', 'pyproject.toml', 'setup.py'],
            'R': ['DESCRIPTION', 'renv.lock', 'packrat/packrat.lock'],
            'C++': ['CMakeLists.txt', 'conanfile.txt', 'vcpkg.json']
        }

        # Check for each dependency file in the repository based on the language
        if repository_language in common_dependency_files:
            for dependency_file in common_dependency_files[repository_language]:
                try:
                    repository.get_contents(dependency_file)
                    return True
                except GithubException:
                    continue
        return False

    except RateLimitExceededException:
        # Handle the rate limit error and pause for 15 minutes
        print("GitHub API rate limit exceeded. Sleeping for 15 minutes...")
        time.sleep(15 * 60)  # Sleep for 15 minutes
        return check_requirements(repository_url)  # Retry the same repository

    except Exception as e:
        print(f"Failed to check requirements for {repository_url}: {str(e)}")
        return None  # Return None if there's an error

def is_github_url(url):
    """
    Check if a URL is a valid GitHub URL.
    Args:
    - url (str or None): The URL to check.

    Returns:
    - bool: True if the URL is a valid GitHub repository URL, False otherwise.
    """
    if isinstance(url, str):
        return url.startswith("https://github.com/")
    return False

if __name__ == "__main__":
    # Create an ArgumentParser object
    argument_parser = argparse.ArgumentParser(
        description='Check requirements of GitHub repositories listed in a CSV file.'
    )

    # Add command-line arguments
    argument_parser.add_argument(
        '--input',
        type=str,
        default='../collect_repositories/results/repositories_filtered.csv',
        help='Input CSV file containing GitHub repository URLs'
    )

    argument_parser.add_argument(
        '--output', 
        type=str,
        default='results/soft_dev_pract.csv',
        help='Output CSV file to save results'
    )

    # Parse command-line arguments
    command_line_arguments = argument_parser.parse_args()

    # Read the input CSV file using pandas
    input_data = pd.read_csv(command_line_arguments.input, sep=',')

    # Add a new column for the results
    input_data['requirements_defined'] = ''

    # Loop through each row of the DataFrame
    for index, row in input_data.iterrows():
        repo_url = row['html_url']

        # Skip rows with missing or non-string GitHub URLs
        if not is_github_url(repo_url):
            print(f"Skipping invalid or non-GitHub URL: {repo_url}")
            input_data.at[index, 'requirements_defined'] = None  # Leave the field empty
            continue

        # Check requirements for each repository using 'repo_url'
        result = check_requirements(repo_url)

        # Set the result in the new column (leave as None if an error occurred)
        input_data.at[index, 'requirements_defined'] = result

    # Write the updated DataFrame to the output CSV file, keeping all original columns
    input_data.to_csv(command_line_arguments.output, index=False)

    print(f"Results saved to {command_line_arguments.output}")
