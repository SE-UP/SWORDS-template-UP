#!/usr/bin/env python3
"""
README Keyword Analyzer

This script analyzes README content in a CSV file of GitHub repositories,
searching for the presence of installation and usage-related keywords.

It adds the following columns to each row:
- installation_keywords: list of matched installation keywords
- usage_keywords: list of matched usage keywords
- installation: True if any installation keyword is found
- usage: True if any usage keyword is found

It also normalizes the 'Language' column, mapping all non-target languages
to 'Other'. The CSV file is overwritten with the updated content.

Usage:
    python keywords_eval_readme.py path/to/file.csv
"""

import argparse
import os
import re
import pandas as pd

# Constants for keyword categories and target languages
KEYWORDS = {
    "installation": ["quick start guide", "getting started", "installation"],
    "usage": ["usage", "examples", "tutorial"]
}
TARGET_LANGUAGES = ["Python", "R", "C++"]

def search_keywords(text, keyword_list):
    """
    Search for keywords in the given text.

    Args:
        text (str): The README content.
        keyword_list (list of str): List of keywords to search for.

    Returns:
        list of str: Keywords found in the text (case-insensitive match).
    """
    found = []
    for keyword in keyword_list:
        if re.search(rf"\b{re.escape(keyword)}\b", str(text), re.IGNORECASE):
            found.append(keyword)
    return found

def normalize_language(language):
    """
    Normalize the language value to one of the target languages or 'Other'.

    Args:
        language (str): The original language string.

    Returns:
        str: Normalized language ('Python', 'R', 'C++', or 'Other').
    """
    return language if language in TARGET_LANGUAGES else "Other"

def process_csv(input_path):
    """
    Load, process, and update the CSV with keyword-based metadata.

    Args:
        input_path (str): Path to the CSV file to process.

    Raises:
        KeyError: If any required column is missing.
        pd.errors.ParserError: If the file cannot be parsed.
    """
    try:
        df = pd.read_csv(input_path, sep=",", on_bad_lines="skip")
        print(f"Data loaded successfully from {input_path}.")
    except pd.errors.ParserError as parse_err:
        print(f"Error parsing the file: {parse_err}")
        raise

    required_columns = ['readme', 'html_url', 'Language']
    for col in required_columns:
        if col not in df.columns:
            raise KeyError(f"Column '{col}' not found in the CSV file.")

    # Apply keyword search and create new columns
    for category, kw_list in KEYWORDS.items():
        df[f"{category}_keywords"] = df["readme"].apply(lambda text: search_keywords(text, kw_list))
        df[category] = df[f"{category}_keywords"].apply(lambda x: bool(x))

    # Normalize the Language column
    df["Language"] = df["Language"].apply(normalize_language)

    # Save updated CSV
    df.to_csv(input_path, index=False)
    print(f"✅ Updated CSV file saved to {input_path}")

def main():
    """
    Main entry point for the script. Parses arguments and triggers processing.
    """
    parser = argparse.ArgumentParser(description="Analyze README keywords in repository metadata.")
    parser.add_argument("csv_path", help="Path to the input CSV file")
    args = parser.parse_args()

    process_csv(args.csv_path)

if __name__ == "__main__":
    main()
