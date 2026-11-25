"""Print the first rows of an MT5 report so its layout can be inspected.

Usage: python scripts/inspect_excel.py <path-to-report.xlsx>
Real reports belong in data/private/ (git-ignored); examples live in data/samples/.
"""

import argparse

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file_path", help="Path to the .xlsx report")
    args = parser.parse_args()

    print(f"Reading file: {args.file_path}")
    df = pd.read_excel(args.file_path, engine="openpyxl", header=None)

    print("\n--- First 20 rows ---")
    for i in range(min(20, len(df))):
        values = [str(v).strip() for v in df.iloc[i].dropna().tolist() if str(v).strip() != ""]
        print(f"Row {i}: {values}")


if __name__ == "__main__":
    main()
