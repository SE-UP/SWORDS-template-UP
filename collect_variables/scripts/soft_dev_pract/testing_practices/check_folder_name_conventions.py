import argparse
import csv
import os
import re
import time
import requests
from ghapi.all import GhApi
from dotenv import load_dotenv

# Get the directory of the current script
script_dir = os.path.dirname(os.path.realpath(__file__))

# Create the relative path to the .env file
env_path = os.path.join(script_dir, '..', '..', '..', '..', '.env')

# Load the .env file
load_dotenv(dotenv_path=env_path, override=True)

# Get the GITHUB_TOKEN and GITHUB_USERNAME from the .env file
token = os.getenv('GITHUB_TOKEN')
username = os.getenv('GITHUB_USERNAME')

# Initialize GhApi instance for GitHub access
gh = GhApi(token=token)

# Folder types to search for
TEST_FOLDERS = [
    "unit", "integration", "system", "e2e", "performance", "regression",
    "functional", "acceptance", "security", "sanity", "mutation", "metamorphic"
]

# Directories to check for Python, C++, and R
PYTHON_CPP_TEST_DIRS = ["test/", "tests/"]
R_TEST_DIRS = ["test/tinytest/", "test/testthat/", "tests/testthat/", "test/tinytest/"]

def search_test_folders(repo_full_name, lang):
    """
    Search for 'test' or 'tests' folders in the root directory and then look for specific subfolders within them.
    """
    print(f"Searching for test folders in repository: {repo_full_name}, Language: {lang}")
    found_folders = []
    other_folders = []

    try:
        # Fetch root-level contents
        root_contents = gh.repos.get_content(*repo_full_name.split("/"), path="")
        print(f"Root contents of {repo_full_name}: {root_contents}")

        # Find root test folders
        root_test_folders = [
            content["path"] for content in root_contents
            if content["type"] == "dir" and content["name"] in ["test", "tests"]
        ]
        print(f"Root test folders: {root_test_folders}")

        # Search inside root test folders
        for test_folder in root_test_folders:
            subcontents = gh.repos.get_content(*repo_full_name.split("/"), path=test_folder)
            print(f"Contents of {test_folder}: {subcontents}")
            for item in subcontents:
                if item["type"] == "dir":
                    if item["name"].lower() in TEST_FOLDERS:
                        found_folders.append(item["name"])
                    else:
                        other_folders.append(item["name"])
    except Exception as e:
        print(f"Error searching folders in repository {repo_full_name}: {e}")

    return list(set(found_folders)), list(set(other_folders))

def process_csv(input_file, output_file):
    """
    Process input CSV, search repositories for test folder names, and write output CSV.
    """
    with open(input_file, newline="") as csvfile:
        reader = csv.DictReader(csvfile, delimiter=",")
        fieldnames = reader.fieldnames + ["test_type", "other_folders"]
        results = []

        for row in reader:
            url = row.get("html_url", "")
            test_folders = []
            other_folders = []

            if "github.com" not in url:
                print(f"Skipping non-GitHub repository: {url}")
                row["test_type"] = []
                row["other_folders"] = []
                results.append(row)
                continue

            while True:
                try:
                    # Extract owner/repo from URL
                    repo_full_name = url.split("github.com/")[1].strip("/")
                    repo = gh.repos.get(*repo_full_name.split("/"))
                    lang = repo["language"].lower() if repo["language"] else None

                    if lang in ["python", "r", "c++"]:
                        print(f"Checking repository: {repo_full_name}, Language: {lang}")
                        test_folders, other_folders = search_test_folders(repo_full_name, lang)
                    else:
                        print(f"Skipping unsupported language ({lang}) in repository: {url}")
                    break  # Exit loop on success
                except requests.exceptions.RequestException as e:
                    if "rate limit exceeded" in str(e).lower():
                        print("Rate limit reached. Sleeping for 20 minutes...")
                        time.sleep(20 * 60)  # Sleep for 20 minutes
                        continue  # Retry after sleeping
                    print(f"Error processing repository {url}: {e}")
                    break  # Skip to next repository
                except Exception as e:
                    if "API rate limit exceeded" in str(e):
                        print("Rate limit exceeded. Sleeping for 20 minutes...")
                        time.sleep(20 * 60)  # Sleep for 20 minutes
                        continue  # Retry after sleeping
                    print(f"Error processing repository {url}: {e}")
                    break  # Skip to next repository

            row["test_type"] = test_folders
            row["other_folders"] = other_folders
            results.append(row)

    # Write output CSV
    with open(output_file, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"Processing complete. Results saved to {output_file}.")

def main():
    parser = argparse.ArgumentParser(description="Check test folders in GitHub repositories.")
    parser.add_argument("--input", required=True, help="Path to input CSV file.")
    parser.add_argument("--output", required=True, help="Path to output CSV file.")
    args = parser.parse_args()

    process_csv(args.input, args.output)

if __name__ == "__main__":
    main()
