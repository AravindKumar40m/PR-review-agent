from agents.llm_client import call_openai
from models import DiffHunk

def style_agent(hunk: DiffHunk):
    prompt = f"""Style reviewer. Look at these added lines and suggest naming, small refactors, docstrings, and readability improvements. Return JSON-list of suggestions."""
    prompt += f"\nFile: {hunk.file_path}\nAdded lines:\n" + "\n".join(hunk.added_lines)
    return call_openai(prompt)
