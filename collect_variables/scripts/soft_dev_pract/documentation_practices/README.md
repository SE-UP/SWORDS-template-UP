# Documentation Practices
This README provides structured, instructions for two documentation checks:

1) **CONTRIBUTING** and **CODE_OF_CONDUCT** presence
2) **Brief comment at start a.k.a module docstring** at the start of source files (`.py`, `.R`, `.cpp`)


To runt the scrits navigate to collect_variables directory. 

## Scripts

### 1) `check_contributing_conduct.py`

**Purpose**  
Checks GitHub repositories for **CONTRIBUTING** and **CODE_OF_CONDUCT** files (e.g., `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`) located in common paths such as repository root, `.github/`, or `docs/`. Saves results to CSV.

**Run (from repository root)**
```bash
python scripts/soft_dev_pract/documentation_practices/check_contributing_conduct.py \
  --input results/repositories.csv \
  --output results/output_results.csv
```

---

### 2) `check_header_comments.py` (generic name)

**Purpose**  
Analyzes repositories for the presence of **brief comments at the start** of source code files (`.py`, `.R`, `.cpp`) and writes results to CSV, including coverage metrics.

> If your actual script filename differs (for example, `check_header_comments.py`, `check_file_headers.py`, etc.), update the path accordingly.

**Run (from `collect_variables` directory)**
```bash
python scripts/soft_dev_pract/documentation_practices/check_header_comments.py \
  --input results/repositories.csv \
  --output results/file_header_comments.csv
```


- **Required columns**
  - `html_url` — Full HTTPS URL of the GitHub repository (e.g., `https://github.com/owner/repo`)

```csv
html_url
https://github.com/owner/repo1
https://github.com/owner/repo2
https://github.com/another-owner/repo3
```