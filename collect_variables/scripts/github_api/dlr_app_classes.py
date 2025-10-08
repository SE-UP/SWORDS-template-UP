"""
Module: classify_dlr

This script reads a CSV file containing a column named 'contributor_count',
classifies each row into a DLR application class based on contributor count,
adds a new column called 'dlr_application_classes', and saves the modified file.

Usage:
    python classify_dlr.py input.csv            # Modifies input.csv in place
    python classify_dlr.py input.csv output.csv # Writes to output.csv

DLR Application Class Rules:
    - Class 0: contributor_count == 1
    - Class 1: 1 < contributor_count <= 3
    - Class 2: contributor_count >= 4
"""

import argparse
import pandas as pd

def classify_contributor_count(count):
    """
    Classify a single contributor count into a DLR application class.

    Parameters:
        count (float or int): The contributor count value.

    Returns:
        int or None: The corresponding DLR application class (0, 1, 2),
                     or None if the count is invalid or missing.
    """
    try:
        count = int(float(count))  #type change to int as we have floar in the csv file.
    except (ValueError, TypeError):
        return None

    if count == 1:
        return 0
    elif 1 < count <= 3:
        return 1
    elif count >= 4:
        return 2
    else:
        return None

def main():
    """
    Main function to parse arguments, classify contributor counts,
    and write the updated CSV file.
    """
    parser = argparse.ArgumentParser(
        description="Classify contributor_count into dlr_application_classes."
    )
    parser.add_argument(
        "input_csv", help="Path to the input CSV file containing 'contributor_count' column"
    )
    parser.add_argument(
        "output_csv",
        nargs="?",
        help="Path to the output CSV file (defaults to modifying the input file)",
    )

    args = parser.parse_args()
    output_path = args.output_csv if args.output_csv else args.input_csv

    # Load the CSV with flexible delimiter detection
    try:
        df = pd.read_csv(args.input_csv, sep=',', engine='python')
    except Exception as e:
        raise RuntimeError(f"Failed to read CSV file: {e}")

    print("Columns found:", df.columns.tolist())  # Debugging aid

    if 'contributor_count' not in df.columns:
        raise ValueError("Input CSV must contain a 'contributor_count' column.")

    # Add classification column
    df['dlr_application_classes'] = df['contributor_count'].apply(classify_contributor_count)

    # Save the modified DataFrame
    df.to_csv(output_path, index=False)

    if args.output_csv:
        print(f"Output written to {output_path}")
    else:
        print(f"Input file '{args.input_csv}' modified in place.")

if __name__ == "__main__":
    main()
