# utils/github_client.py

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

GITHUB_API_BASE = "https://api.github.com"

# base request headers
HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "PR-Review-Agent",
}

if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"token {GITHUB_TOKEN}"


# -----------------------------------------------------------
# ✅ Fetch PR metadata and head commit SHA
# -----------------------------------------------------------
async def fetch_pr_head_sha(owner: str, repo: str, pr_number: int) -> str:
    """
    Returns the HEAD commit SHA of the PR.
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}"

    async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        j = resp.json()
        return j["head"]["sha"]


# -----------------------------------------------------------
# ✅ Fetch PR file list (all changed files)
# -----------------------------------------------------------
async def fetch_pr_files(owner: str, repo: str, pr_number: int):
    """
    Return PR changed files including patches (useful for full PR diffs).
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/files"

    async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()  # list of {filename, patch, changes, ...}


# -----------------------------------------------------------
# ✅ Fetch commit diff (used for latest commit review)
# -----------------------------------------------------------
async def fetch_commit_files(owner: str, repo: str, commit_sha: str):
    """
    Returns list of file dicts (same shape as commit.files from GitHub),
    each may include 'filename' and 'patch'.
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{commit_sha}"

    async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        j = resp.json()
        return j.get("files", [])


# -----------------------------------------------------------
# ✅ Post GitHub Conversation Comment (NOT inline)
# -----------------------------------------------------------
async def post_issue_comment(owner: str, repo: str, pr_number: int, body: str):
    """
    Posts a conversation-level comment (not an inline code comment)
    to a pull request. Equivalent to commenting from the PR UI.
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{pr_number}/comments"

    payload = {"body": body}

    async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as client:
        resp = await client.post(url, json=payload)

        # Raise HTTP errors with full body description
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            # Attach response text for debugging
            raise httpx.HTTPStatusError(
                f"GitHub returned {resp.status_code}: {resp.text}",
                request=e.request,
                response=e.response
            )

        return resp.json()


# -----------------------------------------------------------
# Debug helper (optional): check token availability
# -----------------------------------------------------------
def token_available():
    return bool(GITHUB_TOKEN)
