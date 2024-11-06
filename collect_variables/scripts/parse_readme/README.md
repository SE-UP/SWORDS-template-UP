# Parse GitHub data

Given the (github) API rate limit and time required for parsing varibales for (individual) analysis. We adopted the apporach of getting all the repositoryy content in a csv file and then parsing the variables (keywords for usage, installation, project information, security, usability etc) for analysis.

While extracting README content a problem arised that README content had some similer special characters , ; that resembled the delimiters (characters sperating columns) of csv.  

To address this problem, while saving the readme content to csv file we added new texts before the start and at the end of READMe content (eg. README_start ... README_end) to make this a special delimiter for the column name where the README content is saved. 