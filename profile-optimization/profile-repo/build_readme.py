"""Rewrite the "Recently shipped" section of README.md.

Pulls the latest releases and recently-pushed original (non-fork) repos for
GITHUB_USER and splices them between the `recent_activity` comment markers.
Runs in CI via .github/workflows/build-readme.yml; safe to run locally too:

    GITHUB_TOKEN=... python build_readme.py
"""

import json
import os
import pathlib
import re
import urllib.request

USER = os.environ.get("GITHUB_USER", "ikatyal2110")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
README = pathlib.Path(__file__).parent / "README.md"
MARKER = re.compile(
    r"<!-- recent_activity starts -->.*<!-- recent_activity ends -->",
    re.DOTALL,
)


def gh(url: str):
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
    })
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def recent_items(limit: int = 5) -> list[str]:
    repos = gh(f"https://api.github.com/users/{USER}/repos?sort=pushed&per_page=30")
    items = []
    for repo in repos:
        if repo["fork"] or repo["private"]:
            continue
        releases = gh(repo["releases_url"].replace("{/id}", "?per_page=1"))
        if releases:
            release = releases[0]
            items.append(
                f"- [{repo['name']} {release['tag_name']}]({release['html_url']})"
                f" — {release.get('name') or 'release'}"
                f" ({release['published_at'][:10]})"
            )
        else:
            items.append(
                f"- [{repo['name']}]({repo['html_url']})"
                f" — {repo.get('description') or 'active development'}"
                f" (updated {repo['pushed_at'][:10]})"
            )
        if len(items) >= limit:
            break
    return items


if __name__ == "__main__":
    section = "\n".join([
        "<!-- recent_activity starts -->",
        *recent_items(),
        "<!-- recent_activity ends -->",
    ])
    readme = README.read_text()
    README.write_text(MARKER.sub(section, readme))
    print(f"Updated {README} with {section.count(chr(10)) - 1} items")
