import os
import httpx
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

GITHUB_API_BASE = "https://api.github.com"

HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "PR-Review-Agent",
}

if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"token {GITHUB_TOKEN}"

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


async def fetch_pr_files(owner: str, repo: str, pr_number: int):
    
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/files"

    async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json() 

async def fetch_commit_files(owner: str, repo: str, commit_sha: str):
    
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{commit_sha}"

    async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        j = resp.json()
        return j.get("files", [])

async def post_issue_comment(owner: str, repo: str, pr_number: int, body: str):
    
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{pr_number}/comments"

    payload = {"body": body}

    async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as client:
        resp = await client.post(url, json=payload)

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(
                f"GitHub returned {resp.status_code}: {resp.text}",
                request=e.request,
                response=e.response
            )

        return resp.json()

def token_available():
    return bool(GITHUB_TOKEN)
