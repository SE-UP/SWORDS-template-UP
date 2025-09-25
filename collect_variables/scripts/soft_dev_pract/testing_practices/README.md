# Testing Practices — Folder Conventions & Presence


This README provides structured,  instructions for two testing checks:
1) **Folder name conventions** for Python (`test/`, `tests/`) and R (`test/`, `testthat/`)
2) **Presence of root-level test folders** (`test`, `tests`)

To run the scripts navigate to: 

```bash
cd collect_varaibale
```

## Scripts

### 1) `check_folder_name_conventions.py`

**Purpose**  
Checks types of testing folder conventions by analyzing repository test directories:
- **Python:** `test/` or `tests/`  
- **R:** `test/` or `testthat/`  

**Run (using the same paths as above)**
```bash
python3 scripts/soft_dev_pract/testing_practices/check_folder_name_conventions.py \
  --input results/repositories.csv \
  --output results/test_folder_conventions.csv
```

---

### 2) `test_folder.py`

**Purpose**  
Checks for the presence of **root-level** `test` or `tests` directories in each repository from the CSV.

**Run (using the same paths as above)**
```bash
python3 scripts/soft_dev_pract/testing_practices/test_folder.py \
  --input results/repositories.csv \
  --output results/test_folder_presence.csv
```

---

## Generic Input/Output Schemas

### Input CSV Schema

- **Required columns**
  - `html_url` — Full HTTPS GitHub repo URL (e.g., `https://github.com/owner/repo`)

```csv
html_url
https://github.com/owner/repo1
https://github.com/owner/repo2
https://github.com/another-owner/repo3
```


Todo: 
Artifacts:
1. Presence of TESTING.md
2. Metrics for (Python, R, C++) 

Use LLMs to check 
1. Module (unit, component), integration, system and acceptance. 
2. What should be documented for testing (Test strategy+?): Check if it is present in testing.md
