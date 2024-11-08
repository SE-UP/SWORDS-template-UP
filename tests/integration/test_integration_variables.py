# pylint: skip-file
"""
Tests for retrieval methods in user collection
"""
import pytest

from ghapi.all import GhApi
import time
import pandas as pd

from collect_variables.scripts.github_api.github import (get_data_from_api,
                                                         Service,
                                                         Repo)

from collect_variables.scripts.howfairis_api.howfairis_variables import parse_repo


@pytest.fixture
def repo(*args, **kwargs):
    return Repo(repo_url="https://github.com/utrechtuniversity/swords-uu", repo_owner="utrechtuniversity", repo_repo_name="swords-uu", repo_branch="main")


@pytest.fixture
def repo_coc(*args, **kwargs):
    return Repo(repo_url="https://github.com/asreview/asreview", repo_owner="asreview", repo_repo_name="asreview", repo_branch="master")


@pytest.fixture
def service():
    return Service(api=GhApi(), sleep=10)

@pytest.fixture
def api():
    return GhApi()

"""
Tests for howfairis_variables.py and github.py
"""


def test_get_howfairis_variables(repo: Repo, api: GhApi):
    result = parse_repo(repo.url, api)
    time.sleep(10)
    assert len(result) == 6


def test_get_contributor_variables(repo: Repo, service: Service):
    serv = service
    repository = repo
    retrieved_data = get_data_from_api(serv, repository, "contributors")

    # Print the data structure for debugging
    print("Retrieved data structure:", retrieved_data[0])

    # Check that the retrieved data has the expected number of elements and content
    assert isinstance(retrieved_data[0], list)
    assert len(retrieved_data[0]) >= 3  # Check for at least 3 items as per the original structure
    assert 'https://github.com/utrechtuniversity/swords-uu' in retrieved_data[0]  # Check if the repo URL is present
    assert 'kequach' in retrieved_data[0]  # Check if a contributor's username is present
    

def test_get_language_variables(repo: Repo, service: Service):
    serv = service
    repository = repo
    # get_data_from_api(serv, repository, "contributors")
    retrieved_data = get_data_from_api(serv, repository, "languages")
    assert len(retrieved_data[0]) == 3


def test_get_readme(repo: Repo, service: Service):
    serv = service
    repository = repo
    retrieved_data = get_data_from_api(serv, repository, "readmes")
    print(retrieved_data)
    assert "Scan and revieW of Open Research Data and Software" in retrieved_data[1]


def test_get_file_variables(repo: Repo, service: Service):
    serv = service
    serv.file_list = ["readme"]
    repository = repo
    retrieved_data = get_data_from_api(serv, repository, "files")
    assert len(retrieved_data[0]) == 2


def test_get_test_variables(repo: Repo, service: Service):
    serv = service
    repository = repo
    retrieved_data = get_data_from_api(serv, repository, "tests")
    assert len(retrieved_data[0]) == 2