Adding external users or the users which were not found using methods of collection 


If a user is not found using any of the methods (github_search, papers_with_code, github_org_commit), or if a user wants to be part of this analysis, they can be added manually. 

To do this, create a CSV file in the `results` folder. The CSV file should have the following format:



| service    | date       | user_id  |
| ---------- | ---------- | -------- |
| github.com | 2021-12-02 | kequach  |
| github.com | 2021-12-02 | J535D165 |