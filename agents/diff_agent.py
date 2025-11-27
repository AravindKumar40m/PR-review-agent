from typing import List
from models import DiffHunk

def diff_agent_summarize(hunks: List[DiffHunk]) -> List[dict]:
    summaries = []
    for h in hunks:
        summaries.append({
            "file": h.file_path,
            "added_count": len(h.added_lines),
            "removed_count": len(h.removed_lines),
            "start_line": h.start_line,
            "sample_added": (h.added_lines[:5])
        })
    return summaries
