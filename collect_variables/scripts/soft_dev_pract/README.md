Collecting varibales recommended from   **[Best Practices for Scientific Computing](https://journals.plos.org/plosbiology/article?id=10.1371%2Fjournal.pbio.1001745)** (PLOS Biology) and **[Best Practices for Scientific Computing: A Survey](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005510)** (PLOS Computational Biology) for opensource github repostiores. 



Makind depedency requirements explicit -
            'Python': ['requirements.txt', 'Pipfile', 'pyproject.toml', 'setup.py'],
            'R': ['DESCRIPTION', 'renv.lock', 'packrat/packrat.lock'],
            'C++': ['CMakeLists.txt', 'conanfile.txt', 'vcpkg.json']

            To run it 

 python3 scripts/soft_dev_pract/requirements_explicit.py --input results/repository_links_copy.csv --output results/repository_links_copy.csv