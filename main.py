import os
from collections import defaultdict
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

from diff_parser import parse_unified_diff
from agents.diff_agent import diff_agent_summarize
from agents.logic_agent import logic_agent
from agents.security_agent import security_agent
from agents.style_agent import style_agent
from agents.writer_agent import writer_agent
from models import ReviewResponse, ReviewComment, DiffHunk

from utils.github_client import (
    fetch_pr_files,
    fetch_pr_head_sha,
    fetch_commit_files,
    post_issue_comment,
)

app = FastAPI(title="PR Review Agent (GitHub-enabled)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PRInput(BaseModel):
    owner: str
    repo: str
    pr_number: int

class PostCommentsInput(BaseModel):
    owner: str
    repo: str
    pr_number: int
    comments: List[ReviewComment]

def analyze_hunks_grouped(hunks: List[DiffHunk]) -> ReviewResponse:
 
    if not hunks:
        raise HTTPException(status_code=400, detail="No hunks provided")

    _ = diff_agent_summarize(hunks)

    hunks_by_file = defaultdict(list)
    for h in hunks:
        hunks_by_file[h.file_path].append(h)

    collected = []
    for file_path, file_hunks in hunks_by_file.items():
        merged_added = []
        merged_removed = []
        start_line = None
        for h in file_hunks:
            if start_line is None:
                start_line = h.start_line
            if h.added_lines:
                merged_added.append(f"# --- hunk start (orig_start={h.start_line}) ---")
                merged_added.extend(h.added_lines)
            if h.removed_lines:
                merged_removed.append(f"# --- removed hunk (orig_start={h.start_line}) ---")
                merged_removed.extend(h.removed_lines)

        merged = DiffHunk(
            file_path=file_path,
            added_lines=merged_added,
            removed_lines=merged_removed,
            start_line=start_line
        )

        try:
            la = logic_agent(merged)
        except Exception as e:
            la = [{
                "file": file_path,
                "line": start_line,
                "category": "info",
                "severity": "low",
                "comment": f"Logic agent error: {e}",
                "suggestion": None
            }]
        try:
            sa = security_agent(merged)
        except Exception as e:
            sa = [{
                "file": file_path,
                "line": start_line,
                "category": "info",
                "severity": "low",
                "comment": f"Security agent error: {e}",
                "suggestion": None
            }]
        try:
            st = style_agent(merged)
        except Exception as e:
            st = [{
                "file": file_path,
                "line": start_line,
                "category": "info",
                "severity": "low",
                "comment": f"Style agent error: {e}",
                "suggestion": None
            }]

        collected.extend([la, sa, st])

    final = writer_agent(collected)

    comments: List[ReviewComment] = []
    if isinstance(final, list):
        for c in final:
            try:
                comments.append(ReviewComment(**c))
            except Exception:
                if isinstance(c, dict):
                    comments.append(ReviewComment(
                        file=c.get("file", "unknown"),
                        line=c.get("line"),
                        category=c.get("category", "info"),
                        severity=c.get("severity", "low"),
                        comment=c.get("comment", str(c)),
                        suggestion=c.get("suggestion")
                    ))
                else:
                    comments.append(ReviewComment(
                        file="unknown",
                        line=None,
                        category="info",
                        severity="low",
                        comment=str(c),
                        suggestion=None
                    ))
    else:
        comments.append(ReviewComment(
            file="unknown", line=None, category="info", severity="low",
            comment=str(final), suggestion=None
        ))

    return ReviewResponse(review_summary=f"{len(comments)} comments generated", comments=comments)

def analyze_diff_text(diff_text: str) -> ReviewResponse:
    hunks = parse_unified_diff(diff_text)
    if not hunks:
        raise HTTPException(status_code=400, detail="No hunks parsed from diff")
    return analyze_hunks_grouped(hunks)

@app.post("/review-diff", response_model=ReviewResponse, summary="Review a unified diff (plain text)")
async def review_diff(diff_text: str = Body(..., media_type="text/plain", description="Paste the full unified diff here (plain text).")):
    
    return analyze_diff_text(diff_text)


@app.post("/review-pr", response_model=ReviewResponse, summary="Fetch a GitHub PR and review only its latest commit (HEAD)")
async def review_pr(inp: PRInput):
    
    try:
        head_sha = await fetch_pr_head_sha(inp.owner, inp.repo, inp.pr_number)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch PR metadata from GitHub: {e}")

    if not head_sha:
        raise HTTPException(status_code=404, detail="PR head SHA not found")

    try:
        files = await fetch_commit_files(inp.owner, inp.repo, head_sha)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch commit files for head sha {head_sha}: {e}")

    if not files:
        raise HTTPException(status_code=404, detail="No files returned for head commit")

    patches = []
    for f in files:
        patch = f.get("patch")
        filename = f.get("filename")
        if patch and filename:
            header = f"diff --git a/{filename} b/{filename}\n"
            patches.append(header + patch)

    if not patches:
        raise HTTPException(status_code=400, detail="No patch data available in head commit (binary files or no changes)")

    diff_text = "\n".join(patches)
    return analyze_diff_text(diff_text)

@app.post("/review-pr-and-post-latest")
async def review_pr_and_post_latest(inp: PRInput):
    
    review = await review_pr(inp) 
    posted = []
    errors = []

    for c in review.comments:

        body_lines = [
            f"**File:** {c.file}",
            f"**Line:** {c.line}",
            f"**Category:** {c.category}",
            f"**Severity:** {c.severity}",
            "",
            f"**Comment:**\n{c.comment}"
        ]
        if c.suggestion:
            body_lines.extend(["", f"**Suggestion:**\n{c.suggestion}"])
        body = "\n".join(body_lines)

        try:
            res = await post_issue_comment(inp.owner, inp.repo, inp.pr_number, body)
            posted.append({
                "status": "ok",
                "id": res.get("id"),
                "html_url": res.get("html_url"),
                "created_at": res.get("created_at"),
                "body_preview": (res.get("body") or "")[:300]
            })
        except Exception as e:
            errors.append({"status": "error", "message": str(e), "comment_preview": body[:300]})

    return {"review": review, "posted": posted, "errors": errors}

@app.get("/")
def root():
    return {"status": "PR Review Agent running", "git_integration": bool(os.getenv("GITHUB_TOKEN"))}
