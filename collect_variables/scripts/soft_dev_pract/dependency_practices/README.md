
# Dependency Practices — Lock & Explicit Requirements

This README provides structured instructions to run dependency-related data collection scripts for **Python**, **R**, and **C++**.



navigate to: 
```bash
cd collect_variables
```

## Scripts

### 1) `dependency_lock_files.py`

**Purpose**  
Retrieve dependency **`.lock`** files for **Python**, **R**, and **C++** from repositories listed in the input CSV, and record findings to an output CSV.

**Run**
```bash
python dependency_lock_files.py \
  --input <input_csv_file> \
  --output <output_csv_file>
```

### 2) `requirement_explicit.py`

**Purpose**  
Retrieve explicit dependency requirement files (e.g., `requirements.txt`, `DESCRIPTION`, `renv.lock`, `Conan`/`vcpkg` manifests) for **Python**, **R**, and **C++**, and record findings to an output CSV.

**Run**
```bash
python3 scripts/soft_dev_pract/dependency_practices/requirement_explicit.py \
  --input <input_csv_file> \
  --output <output_csv_file>
```

## Example `input file`

```csv
html_url
https://github.com/owner/repo1
https://github.com/owner/repo2
https://github.com/another-owner/repo3
```