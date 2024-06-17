"""
This program finds certain keywords in the README.md.
"""

import re
import argparse
import pandas as pd

# Define the keywords for reproducibility and security
REPRODUCIBILITY_KEYWORDS = [
    'installation', 'setup', 'usage', 'docker',
    'containerisation', 'versioning', 'data'
]
SECURITY_KEYWORDS = [
    'security', 'authentication', 'encryption', 'access control',
    'audit', 'logging', 'updates', 'patches',
    'penetration testing', 'vulnerability testing'
]


def check_keywords(text, keywords):
    """
    Check if any of the keywords are present in the text.

    Parameters:
    text (str): The text to check.
    keywords (list): The list of keywords to check for.

    Returns:
    bool: True if any keyword is found, False otherwise.
    """
    for keyword in keywords:
        # Check for the keyword with markdown formatting
        if re.search(rf"\b{keyword}\b", text, re.IGNORECASE):
            return True
    return False


def main(csv_file):
    """
    Main function to read the CSV file, check the repositories,
      and update the CSV file.

    Parameters:
    csv_file (str): The path to the CSV file.
    """
    data_frame = pd.read_csv(csv_file, sep=',', on_bad_lines='warn')
    if 'reproduce' not in data_frame.columns:
        data_frame['reproduce'] = False
    if 'security' not in data_frame.columns:
        data_frame['security'] = False

    for index, row in data_frame.iterrows():
        readme = row['readme']
        if pd.isnull(readme):
            continue
        data_frame.loc[index, 'reproduce'] = check_keywords(readme, REPRODUCIBILITY_KEYWORDS)
        data_frame.loc[index, 'security'] = check_keywords(readme, SECURITY_KEYWORDS)

    data_frame.to_csv(csv_file, index=False)


if __name__ == "__main__":
    ARGUMENT_PARSER = argparse.ArgumentParser(
        description='Check for test folders in GitHub repositories.')
    ARGUMENT_PARSER.add_argument('csv_file', type=str, help='Input CSV file')
    ARGUMENTS = ARGUMENT_PARSER.parse_args()
    main(ARGUMENTS.csv_file)
