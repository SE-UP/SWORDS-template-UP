test_folder.py - checks if the folder named test or tests is present in the root directory of github repository or not. 
to run the test_folder.py use the following command in the collect_varibales 
 python3 scripts/soft_dev_pract/test_folder.py results/user_research_repos_test.csv

continious_integration.py - checks if the github_actions is implemented or not is present in the root directory of github repository or not. 
to run the continious_integration.py use the following command in the collect_varibales 
 python3 scripts/soft_dev_pract/continious_integration.py results/user_research_repos_test.csv

add_ci_rules.py - checks if additional rules are present in the yaml or yml file for linters and testing for languages python,R and cpp
 to run the program add_ci_rules.py use the following command in the collect_varibales 
 python3 scripts/soft_dev_pract/add_ci_rules.py results/user_research_repos_test.csv

comment_at_start.py -  Chekcs the presence of comments at the start of source code files in GitHub repositories.
To run the comment_at_start.py program use following command 
python3 scripts/soft_dev_pract/comment_at_start.py results/final_data_publish.csv