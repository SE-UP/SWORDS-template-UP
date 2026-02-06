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
- **Python and C++:** `test/` or `tests/`  
- **R:** `test/testthat` or `tests/testthat` or `test/tinytest` or `tests/tinytest` 

**Run (using the same paths as above)**
```bash
python3 scripts/soft_dev_pract/testing_practices/check_folder_name_conventions.py \
  --input results/repositories.csv \
  --output results/test_folder_conventions.csv
```

To get the language column run script enrich_repo_data.py

```csv
html_url, Language
https://github.com/owner/repo1, Python
https://github.com/owner/repo2, R
https://github.com/another-owner/repo3, C++
```


---

### 2) `test_folder.py`

**Purpose**  
Checks for the presence of **root-level** `test` or `tests` or `*test*`directories in each repository from the CSV. And check if the folder is non empty traverse into (sub)folder of detected test folder and find out programming language found (Python, R, C++ or bash) stops when found (only ensures presence of programming language script in the folder). 

**Run (using the same paths as above)**
```bash
python3 scripts/soft_dev_pract/testing_practices/test_folder.py \
  --input results/repositories.csv \
  --output results/test_folder_presence.csv
```

---


### 2) `check_perf_bench.py`

**Purpose**  
Checks for the presence of **root-level** `*performance*` or `*benchmark*` or `*perf*` or `*bench*` directories in each repository from the CSV.

**Run**
```bash
python3 scripts/soft_dev_pract/testing_practices/check_perf_bench.py \
  --input results/repositories.csv \
  --output results/test_folder_presence.csv
```

Note: As it looks for folder names that contains `*perf*` and `*bench*` there is need to manually check the results for false positive. 
---

### Input CSV 

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
