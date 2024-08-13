"""
This script processes the 'readme' column in a CSV file by adding specific delimiters 
around its content to ensure that the entire content fits within a single cell, even if 
it contains special characters or other delimiters. The processed CSV file is then saved 
to a specified output location.
"""

import argparse
import pandas as pd


def process_readme_column(input_csv, output_csv, delimiter=','):
    """
    Process the 'readme' column in the CSV file to change its delimiter.

    Args:
        input_csv (str): Path to the input CSV file.
        output_csv (str): Path to save the output CSV file.
        delimiter (str): The delimiter to use for the readme content.
    """
    try:
        # Read the CSV file
        data_frame = pd.read_csv(input_csv, sep=delimiter, engine='python')

        # Process the 'readme' column to replace delimiters inside it
        if 'readme' in data_frame.columns:
            data_frame['readme'] = data_frame['readme'].apply(
                lambda x: f"README_start {str(x)} README_end"
            )
        else:
            print("The 'readme' column does not exist in the input CSV file.")
            return

        # Save the updated CSV file
        data_frame.to_csv(output_csv, sep=delimiter, index=False)
        print(f"Processed CSV saved to {output_csv}")

    except FileNotFoundError:
        print(f"File {input_csv} not found.")
    except pd.errors.ParserError:
        print(f"Parsing error occurred while reading {input_csv}.")
    except Exception as error:  # Catching a more specific error
        print(f"An error occurred: {error}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process the 'readme' column in a CSV file to change its delimiter."
    )
    parser.add_argument('--input', required=True, help="Path to the input CSV file.")
    parser.add_argument('--output', required=True, help="Path to save the output CSV file.")
    parser.add_argument(
        '--delimiter', default=',', help="Delimiter to use in the CSV file (default is ',')."
    )

    arguments = parser.parse_args()

    process_readme_column(arguments.input, arguments.output, arguments.delimiter)
