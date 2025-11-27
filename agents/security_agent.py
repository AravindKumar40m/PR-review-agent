from agents.llm_client import call_openai
from models import DiffHunk

def security_agent(hunk: DiffHunk):
    prompt = f"""Security analyst. Scan these added lines for vulnerabilities (SQL injection, shell injection, unsafe eval, secrets, insecure configs). Return JSON-list of findings."""
    prompt += f"\nFile: {hunk.file_path}\nAdded lines:\n" + "\n".join(hunk.added_lines)
    return call_openai(prompt)
