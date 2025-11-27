from typing import List
from agents.llm_client import call_openai
from models import DiffHunk

def logic_agent(hunk: DiffHunk):
    prompt = f"""You are a code reviewer. Analyze the added lines in this diff hunk and point out logic errors, incorrect operators, off-by-one, and missing edge cases. Return results as json list with keys: file,line,category,severity,comment,suggestion.

File: {hunk.file_path}
Start_line: {hunk.start_line}
Added lines:
{chr(10).join(hunk.added_lines)}
"""
    out = call_openai(prompt)
    return out  # We'll parse it later or expect LLM to return JSON
