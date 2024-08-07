"""
This program finds (Reproducibility and Security) keywords in the README.md.
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


def main(input_csv):
    """
    Main function to read the CSV file, check the repositories,
    and update the CSV file.

    Parameters:
    input_csv (str): The path to the input CSV file.
    """
    data_frame = pd.read_csv(input_csv, sep=',', on_bad_lines='warn')
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

    data_frame.to_csv(input_csv, index=False)


if __name__ == "__main__":
    ARGUMENT_PARSER = argparse.ArgumentParser(
        description='Check for reproducibility and security keywords in README files.')
    ARGUMENT_PARSER.add_argument('--input', type=str, required=True, help='Input CSV file')
    ARGUMENTS = ARGUMENT_PARSER.parse_args()
    main(ARGUMENTS.input)
