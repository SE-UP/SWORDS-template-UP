Executable command for enrich_repo_data.py  

python scripts/github_api/enrich_repo_data.py --input results/joss_all.csv --output results/joss_all_language.csv


Note: 
enrich_repo_data.py creates duplicate records when it runs into error while api rate limit (this is our assumption after seeing logs) and the record is saved multiple times (4 addressed during manual inspection) as number of records did not matched with the output csv file. For optimal results create another output csv file and delete the redundant records. 

# GitHub API
This folder holds the code for variables that are retrieved by GitHub API.
