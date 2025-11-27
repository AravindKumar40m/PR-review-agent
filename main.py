# # main.py
# from fastapi import FastAPI, HTTPException, Body
# from typing import List
# from dotenv import load_dotenv

# from diff_parser import parse_unified_diff
# from agents.diff_agent import diff_agent_summarize
# from agents.logic_agent import logic_agent
# from agents.security_agent import security_agent
# from agents.style_agent import style_agent
# from agents.writer_agent import writer_agent
# from models import ReviewResponse, ReviewComment

# load_dotenv()

# app = FastAPI(title="PR Review Agent")

# @app.post("/review-diff", response_model=ReviewResponse, summary="Review a unified diff (plain text)")
# async def review_diff(diff_text: str = Body(..., media_type="text/plain", description="Paste the full unified diff here (plain text).")):
#     hunks = parse_unified_diff(diff_text)
#     if not hunks:
#         raise HTTPException(status_code=400, detail="No hunks parsed from diff")

#     # quick summary from diff agent (unused in response but kept for pipeline)
#     summaries = diff_agent_summarize(hunks)

#     # call other agents for each hunk (sequential for now)
#     collected = []
#     for h in hunks:
#         # skip hunks without added lines
#         if not h.added_lines:
#             continue
#         collected.append(logic_agent(h))
#         collected.append(security_agent(h))
#         collected.append(style_agent(h))

#     # Final aggregator - ask writer agent to produce JSON
#     final = writer_agent(collected)

#     # if writer_agent returned JSON list, coerce into ReviewComment objects
#     comments: List[ReviewComment] = []
#     if isinstance(final, list):
#         for c in final:
#             try:
#                 comments.append(ReviewComment(**c))
#             except Exception:
#                 # Be forgiving: convert partial dicts / malformed items into a safe ReviewComment
#                 if isinstance(c, dict):
#                     comments.append(ReviewComment(
#                         file=c.get("file", "unknown"),
#                         line=c.get("line"),
#                         category=c.get("category", "info"),
#                         severity=c.get("severity", "low"),
#                         comment=c.get("comment", str(c)),
#                         suggestion=c.get("suggestion")
#                     ))
#                 else:
#                     comments.append(ReviewComment(
#                         file="unknown",
#                         line=None,
#                         category="info",
#                         severity="low",
#                         comment=str(c),
#                         suggestion=None
#                     ))
#     else:
#         # fallback: return a single comment with the text
#         comments.append(ReviewComment(
#             file="unknown", line=None, category="info", severity="low",
#             comment=str(final), suggestion=None
#         ))

#     return ReviewResponse(review_summary=f"{len(comments)} comments", comments=comments)



# main.py
import os
from collections import defaultdict
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv

# ensure .env loaded early
load_dotenv()

# local project imports (utils must contain github_client with helper functions)
from diff_parser import parse_unified_diff
from agents.diff_agent import diff_agent_summarize
from agents.logic_agent import logic_agent
from agents.security_agent import security_agent
from agents.style_agent import style_agent
from agents.writer_agent import writer_agent
from models import ReviewResponse, ReviewComment, DiffHunk

# GitHub helpers (fetch_pr_head_sha, fetch_commit_files, post_issue_comment)
from utils.github_client import (
    fetch_pr_files,
    fetch_pr_head_sha,
    fetch_commit_files,
    post_issue_comment,
)

app = FastAPI(title="PR Review Agent (GitHub-enabled)")

# DEVELOPMENT CORS - allow all origins for local testing (restrict in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- request models ---
class PRInput(BaseModel):
    owner: str
    repo: str
    pr_number: int

class PostCommentsInput(BaseModel):
    owner: str
    repo: str
    pr_number: int
    comments: List[ReviewComment]

# --- helper: analyze hunks grouped by file (batch per-file) ---
def analyze_hunks_grouped(hunks: List[DiffHunk]) -> ReviewResponse:
    """
    Given a list of DiffHunk objects (from parse_unified_diff),
    group them per-file, merge added lines per file, call agents once per file,
    aggregate responses using writer_agent, and return ReviewResponse.
    """
    if not hunks:
        raise HTTPException(status_code=400, detail="No hunks provided")

    # optional quick summary
    _ = diff_agent_summarize(hunks)

    # group hunks by file
    hunks_by_file = defaultdict(list)
    for h in hunks:
        hunks_by_file[h.file_path].append(h)

    collected = []
    for file_path, file_hunks in hunks_by_file.items():
        # Merge added/removed lines, keeping small separators so LLM can see hunk boundaries
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

        # call agents once per file; each agent returns list/dict/text
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

    # aggregate via writer agent
    final = writer_agent(collected)

    # coerce into ReviewComment objects with forgiving parsing
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

# --- helper: parse unified diff text into hunks ---
def analyze_diff_text(diff_text: str) -> ReviewResponse:
    hunks = parse_unified_diff(diff_text)
    if not hunks:
        raise HTTPException(status_code=400, detail="No hunks parsed from diff")
    return analyze_hunks_grouped(hunks)

# --- endpoints ---

@app.post("/review-diff", response_model=ReviewResponse, summary="Review a unified diff (plain text)")
async def review_diff(diff_text: str = Body(..., media_type="text/plain", description="Paste the full unified diff here (plain text).")):
    """Manual endpoint: accepts raw unified diff as text/plain."""
    return analyze_diff_text(diff_text)


@app.post("/review-pr", response_model=ReviewResponse, summary="Fetch a GitHub PR and review only its latest commit (HEAD)")
async def review_pr(inp: PRInput):
    """
    Fetch the PR's HEAD commit files, combine patches into a single diff,
    and run the analyzer. This reviews only the latest commit in the PR.
    """
    # get head commit sha
    try:
        head_sha = await fetch_pr_head_sha(inp.owner, inp.repo, inp.pr_number)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch PR metadata from GitHub: {e}")

    if not head_sha:
        raise HTTPException(status_code=404, detail="PR head SHA not found")

    # fetch commit files for the head commit
    try:
        files = await fetch_commit_files(inp.owner, inp.repo, head_sha)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch commit files for head sha {head_sha}: {e}")

    if not files:
        raise HTTPException(status_code=404, detail="No files returned for head commit")

    # build per-file diffs with headers so unidiff parses them
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


# Posts review comments (conversation comments) for the HEAD commit analysis
@app.post("/review-pr-and-post-latest")
async def review_pr_and_post_latest(inp: PRInput):
    """
    Review the PR HEAD commit and post generated comments as issue comments on the PR.
    Returns the review and posted comment metadata or errors per comment.
    """
    review = await review_pr(inp)  # uses HEAD commit
    posted = []
    errors = []

    for c in review.comments:
        # compose a clear human readable comment body
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
            # collect error details but continue processing other comments
            errors.append({"status": "error", "message": str(e), "comment_preview": body[:300]})

    return {"review": review, "posted": posted, "errors": errors}


# --- simple root ---
@app.get("/")
def root():
    return {"status": "PR Review Agent running", "git_integration": bool(os.getenv("GITHUB_TOKEN"))}
