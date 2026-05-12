# CI & Automation Practices

This README provides structured instructions to run CI-related data collection scripts (**pre-commit hooks**, **pre-merge/CI checks**) and additional automation practices (**lint**, **build**, **test**).

To run the scripts navigate to: 

```bash
cd collect_varaibale
```
make sure you are in SWORDS-template-UP/collect_variables folder before you run following commands in terminal. 
create .venv (using: .venv\Scripts\activate) install dependencies(using: pip install -r requirements.txt) 

## Scripts

### 1) `check_pre_commit_hooks.py`

**Purpose**  
Detects whether repositories include a `.pre-commit-config.yaml` and logs results to CSV. (only checks presence of pre-commit-hooks)

**Run**
```bash
python3 scripts/soft_dev_pract/ci_practices/check_pre_commit_hooks.py \
  --input results/repository_links.csv \
  --output results/ci_hooks.csv
```

---

### 2) `continious_integration.py`

**Purpose**  
Checks for CI configuration (e.g., `.github` for GitHub Actions, and other CI tools like Travis CI, CircleCI, etc.) in repository roots (only checks presence of those tools).

**Run**
```bash
python3 scripts/soft_dev_pract/ci_practices/continious_integration.py \
  --input results/repository_links.csv \
  --output results/output.csv
```

---

### 3) `add_ci_rules.py`

**Purpose**  
Scans YAML files in `.github/workflows/` to detect testing libraries and linters for **Python**, **R**, and **C++**.

**Run**
```bash
python3 scripts/soft_dev_pract/ci_practices/add_ci_rules.py \
  --input results/repository_links.csv \
  --output results/output.csv
```

---

### 4) `add_ci_test_rule.py`

**Purpose**  
Scans YAML files in CI tools to detect testing libraries for **Python**, **R**, and **C++** (requires additional columns 'Language' collected through enrich_repo.py and 'continious_integration' aquired through continious_integration.py).

**Run**
```bash
python3 scripts/soft_dev_pract/ci_practices/add_ci_test_rule.py \
  --input results/repository_links.csv \
  --output results/output.csv
```
It creates following columns as output 

| Column name               | In 3 words        |
|---------------------------|-------------------|
| `ci_tool_detected`        | Detected CI tools |
| `test_rule_in_ci`         | Test keywords present |
| `file_ci_test_rule_found` | YAML files matched |
| `test_keyword_found`      | Matched keywords  |

Note before running abvoe script make sure you have required columns to do furhter analysis. You need to collect those columns by running github_api/enrich_repo_data.py (this will generate required column Language) 

---

### 5) `check_pre_commit_auto_test.py`

**Purpose**  
Detects whether repositories include a `.pre-commit-config.yaml` and testing libraries and commands for **Python**, **R**, and **C++**  in repository and logs results to CSV. 

**Run**
```bash
python3 scripts/soft_dev_pract/ci_practices/check_pre_commit_auto_test.py \
  --input results/joss_published_20260506.csv \
  --output results/joss_published_20260506_pre_commit.csv
```
It creates following columns as output 




---


### 6) `check_pre_commit_auto_test.py`

**Purpose**  
Detects presence of continious integration tool and then checks YAML file in CI tools to detect testing libraries for **Python**, **R**, and **C++**.

**Run**
```bash
python3 scripts/soft_dev_pract/ci_practices/check_pre_commit_auto_test.py \
  --input results/joss_published_20260506.csv \
  --output results/joss_published_20260506_pre_commit.csv
```
Note: sometime having \ in the command gives error like check_ci_auto_test.py: error: the following arguments are required: -i/--input, -o/--output while it works if you simply remove those next line  \ 




---





## Example `input file`

```csv
html_url
https://github.com/owner/repo1
https://github.com/owner/repo2
https://github.com/another-owner/repo3
```


