from unidiff import PatchSet
from typing import List
from models import DiffHunk

def parse_unified_diff(diff_text: str) -> List[DiffHunk]:
    patch = PatchSet(diff_text.splitlines(keepends=True))
    hunks = []
    for patched_file in patch:
        file_path = patched_file.path
        for hunk in patched_file:
            added = []
            removed = []
            for line in hunk:
                if line.is_added:
                    added.append(line.value.rstrip('\n'))
                elif line.is_removed:
                    removed.append(line.value.rstrip('\n'))
            hunks.append(DiffHunk(file_path=file_path,
                                  added_lines=added,
                                  removed_lines=removed,
                                  start_line=hunk.target_start))
    return hunks
