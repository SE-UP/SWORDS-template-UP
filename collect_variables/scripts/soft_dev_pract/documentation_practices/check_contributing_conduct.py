"""
Python script to check if GitHub repositories have CONTRIBUTING.md and CODE_OF_CONDUCT.md.
- Checks root directory, `.github/`, and `docs/` folders.
- Uses ghapi and a GitHub token for authentication.
- Skips repositories on error or non-GitHub domains but retains all rows in the output CSV.
"""

import os
import argparse
import pandas as pd
from ghapi.all import GhApi
from dotenv import load_dotenv


def check_repository_files(api, repo_owner, repo_name):
    """
    Check if the repository has CONTRIBUTING.md and CODE_OF_CONDUCT.md files.
    Searches in the root directory, `.github/`, and `docs/` folders.
    """
    paths_to_check = [
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        ".github/CONTRIBUTING.md",
        ".github/CODE_OF_CONDUCT.md",
        "docs/CONTRIBUTING.md",
        "docs/CODE_OF_CONDUCT.md"
    ]
    for path in paths_to_check:
        try:
            api.repos.get_content(owner=repo_owner, repo=repo_name, path=path)
            return True  # File found
        except Exception:
            continue  # Ignore if file not found or error occurs
    return False


def process_repositories(input_csv, output_csv, token):
    """
    Iterate through repositories from input CSV and check for guidelines.
    Save results to an output CSV.
    """
    # Read the input CSV
    df = pd.read_csv(input_csv)

    # Add columns for results
    df['has_contributing'] = None
    df['has_code_of_conduct'] = None

    api = GhApi(token=token)

    total_repos = len(df)
    completed = 0

    for index, row in df.iterrows():
        try:
            # Skip non-GitHub URLs
            if "github.com" not in row['html_url']:
                print(f"Skipping non-GitHub domain: {row['html_url']}")
                continue

            # Parse repository owner and name from URL
            parts = row['html_url'].replace("https://github.com/", "").split("/")
            if len(parts) < 2:
                continue
            repo_owner, repo_name = parts[0], parts[1]

            # Check for files
            df.at[index, 'has_contributing'] = check_repository_files(api, repo_owner, repo_name)
            df.at[index, 'has_code_of_conduct'] = check_repository_files(api, repo_owner, repo_name)
        except Exception as e:
            print(f"Skipping repository due to error: {row['html_url']} ({e})")
            continue
        finally:
            completed += 1
            print(f"Processed: {completed}/{total_repos}")

    # Save results to output CSV
    df.to_csv(output_csv, index=False)
    print(f"Results saved to {output_csv}")


def main():
    """
    Main function to parse arguments and execute the script.
    """
    # Get the directory of the current script
    script_dir = os.path.dirname(os.path.realpath(__file__))

    # Create the relative path to the .env file
    env_path = os.path.join(script_dir, '..', '..', '..', '..', '.env')

    # Load the .env file
    load_dotenv(dotenv_path=env_path, override=True)

    # Get the GITHUB_TOKEN from the .env file
    token = os.getenv('GITHUB_TOKEN')

    if not token:
        print("GitHub token not found in .env file.")
        return

    # Command-line argument parsing
    parser = argparse.ArgumentParser(description="Check for CONTRIBUTING.md and CODE_OF_CONDUCT.md in GitHub repositories.")
    parser.add_argument("--input", required=True, help="Path to the input CSV file.")
    parser.add_argument("--output", required=True, help="Path to the output CSV file.")
    args = parser.parse_args()

    # Process repositories
    process_repositories(args.input_csv, args.output_csv, token)


if __name__ == "__main__":
    main()
