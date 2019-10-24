import re
from collections import namedtuple
from . import interwebs


GitHubRepo = namedtuple("GitHubRepo", ("url", "fqdn", "owner", "repo"))


def parse_remote_url(remote_url):
    if remote_url.endswith(".git"):
        remote_url = remote_url[:-4]

    if remote_url.startswith("git@"):
        remote_url = remote_url.replace(":", "/").replace("git@", "https://")
    elif remote_url.startswith("git://"):
        remote_url = remote_url.replace("git://", "https://")

    if not remote_url:
        return None

    match = re.match(r"https?://([a-zA-Z-\.0-9]+)/([a-zA-Z-\._0-9]+)/([a-zA-Z-\._0-9]+)/?", remote_url)

    if not match:
        return None

    return GitHubRepo(remote_url, *match.groups())


def query_github(path, github_repo, token=None, headers=None):
    is_enterprise = not github_repo.fqdn.endswith("github.com")

    api_url = "api.github.com" if not is_enterprise else github_repo.fqdn
    base_path = "/api/v3" if is_enterprise else ""
    path = base_path + path
    auth = (token, "x-oauth-basic") if token else None

    response = interwebs.get(api_url, 443, path, https=True, auth=auth, headers=headers)

    return response
