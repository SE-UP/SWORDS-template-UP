"""
This script utilizes the GitHub API to retrieve repository details
and specific files (like requirements.txt, DESCRIPTION, CMakeLists.txt)
that typically document project dependencies.
"""

import argparse
import os
import csv
from dotenv import load_dotenv
from github import Github

# Get the directory of the current script
script_dir = os.path.dirname(os.path.realpath(__file__))

# Create the relative path to the .env file
env_path = os.path.join(script_dir, '..', '..', '..', '.env')

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

        # Check if requirements are made explicit
        if repository_language == 'Python':
            repository.get_contents('requirements.txt')
            return True

        if repository_language == 'R':
            try:
                repository.get_contents('DESCRIPTION')
            except Exception:
                repository.get_contents('packrat/packrat.lock')
            return True

        if repository_language == 'C++':
            repository.get_contents('CMakeLists.txt')
            return True

        return False

    except Exception as e:
        print(f"Failed to check requirements for {repository_url}: {str(e)}")
        return False

if __name__ == "__main__":
    # Create an ArgumentParser object
    argument_parser = argparse.ArgumentParser(
        description='Check requirements of GitHub repositories listed in a CSV file.')
    argument_parser.add_argument('--input', type=str,
                                 default='../collect_repositories/results/repositories_filtered.csv',
                                 help='Input CSV file containing GitHub repository URLs')
    argument_parser.add_argument('--output', type=str, default='results/soft_dev_pract.csv',
                                 help='Output CSV file to save results')

    # Parse command-line arguments
    command_line_arguments = argument_parser.parse_args()

    # Initialize list to store results
    results_list = []

    # Read input CSV file
    with open(command_line_arguments.input, 'r', newline='', encoding='utf-8') as input_csv_file:
        csv_reader = csv.DictReader(input_csv_file)
        for row in csv_reader:
            # Use a different variable name in the inner scope
            repo_url = row['html_url']

            # Check requirements for each repository using 'repo_url'
            result = check_requirements(repo_url)

            # Append result to results list
            results_list.append({'repository_url': repo_url, 'requirements_defined': result})

    # Write results to output CSV file
    with open(command_line_arguments.output, 'w', newline='', encoding='utf-8') as output_csv_file:
        csv_fieldnames = ['repository_url', 'requirements_defined']
        csv_writer = csv.DictWriter(output_csv_file, fieldnames=csv_fieldnames)
        csv_writer.writeheader()
        for result in results_list:
            csv_writer.writerow(result)

    print(f"Results saved to {command_line_arguments.output}")
