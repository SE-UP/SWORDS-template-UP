# CI & Automation Practices

This README provides structured instructions to run CI-related data collection scripts (**pre-commit hooks**, **pre-merge/CI checks**) and additional automation practices (**lint**, **build**, **test**).

To run the scripts navigate to: 

```bash
cd collect_varaibale
```



## Scripts

### 1) `check_pre_commit_hooks.py`

**Purpose**  
Detects whether repositories include a `.pre-commit-config.yaml` and logs results to CSV.

**Run**
```bash
python3 scripts/soft_dev_pract/ci_practices/check_pre_commit_hooks.py \
  --input results/repository_links.csv \
  --output results/ci_hooks.csv
```

---

### 2) `continious_integration.py`

**Purpose**  
Checks for CI configuration (e.g., `.github` for GitHub Actions, and other CI tools like Travis CI, CircleCI, etc.) in repository roots.

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
Scans YAML files in CI tools to detect testing libraries for **Python**, **R**, and **C++**.

**Run**
```bash
python3 scripts/soft_dev_pract/ci_practices/add_ci_test_rule.py \
  --input results/repository_links.csv \
  --output results/output.csv
```

Note before running abvoe script make sure you have required columns to do furhter analysis. You need to collect those columns by running github_api/enrich_repo_data.py (this will generate required column Language) 

---



## Example `input file`

```csv
html_url
https://github.com/owner/repo1
https://github.com/owner/repo2
https://github.com/another-owner/repo3
```


