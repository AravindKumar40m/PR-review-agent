from pydantic import BaseModel
from typing import List, Optional

class DiffHunk(BaseModel):
    file_path: str
    added_lines: List[str]
    removed_lines: List[str]
    start_line: Optional[int] = None

class ReviewComment(BaseModel):
    file: str
    line: Optional[int]
    category: str
    severity: str
    comment: str
    suggestion: Optional[str] = None

class ReviewResponse(BaseModel):
    review_summary: str
    comments: List[ReviewComment]
