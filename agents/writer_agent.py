# from models import ReviewComment
# import json

# def writer_agent(collected_findings_texts: list):
#     # collected_findings_texts: list of strings (LLM outputs)
#     # Simple approach: concatenate and ask LLM to produce final JSON array of ReviewComment
#     from agents.llm_client import call_openai
#     prompt = "You are an aggregator. Combine these findings and produce a JSON array of review comments with fields: file,line,category,severity,comment,suggestion.\n\n" + "\n\n".join(collected_findings_texts)
#     out = call_openai(prompt)
#     try:
#         parsed = json.loads(out)
#         return parsed
#     except Exception:
#         # fallback: return raw text
#         return out


# agents/writer_agent.py
from typing import List, Any
from .llm_client import call_openai
import json

def _stringify_item(item: Any) -> str:
    """
    Convert an agent output item to a string representation safe for joining into a prompt.
    - dict/list -> pretty JSON
    - other -> str()
    """
    if isinstance(item, (dict, list)):
        try:
            return json.dumps(item, indent=2, ensure_ascii=False)
        except Exception:
            # fallback to plain str
            return str(item)
    return str(item)

def _extract_json_from_text(text: str) -> Any:
    """
    Try multiple ways to extract JSON from model text:
    1. Direct json.loads(text)
    2. Find first '[' and last ']' and parse that substring
    3. Find first '{' and last '}' and parse that substring (single object)
    Returns parsed JSON or raises.
    """
    # 1) direct
    try:
        return json.loads(text)
    except Exception:
        pass

    # 2) try to extract array
    s = text
    start = s.find('[')
    end = s.rfind(']')
    if start != -1 and end != -1 and end > start:
        candidate = s[start:end+1]
        try:
            return json.loads(candidate)
        except Exception:
            pass

    # 3) try to extract single object
    start = s.find('{')
    end = s.rfind('}')
    if start != -1 and end != -1 and end > start:
        candidate = s[start:end+1]
        try:
            return json.loads(candidate)
        except Exception:
            pass

    # nothing worked
    raise ValueError("No JSON found in text")

def writer_agent(collected_findings: List[Any]) -> List[dict]:
    """
    Aggregate outputs (which may be lists/dicts or raw text) and ask the LLM
    to produce a single JSON array of standardized review comments.

    Returns a list of dicts (each a review comment). If parsing the LLM response fails,
    returns a single info entry with the raw response embedded.
    """
    # Prepare a combined prompt payload: stringify each collected finding safely
    combined = []
    for f in collected_findings:
        combined.append(_stringify_item(f))

    prompt = (
        "You are an aggregator that merges multiple reviewer findings into a "
        "deduplicated JSON array of review comments. Each review comment object must have: "
        "file (string), line (int|null), category (logic|security|style|info), "
        "severity (low|medium|high), comment (string), suggestion (string|null).\n\n"
        "Combine the collected findings into a single JSON array, deduplicate similar issues, "
        "and be concise.\n\n"
        "Collected findings:\n\n"
        + "\n\n".join(combined)
    )

    out = call_openai(prompt, max_tokens=700)
    # If LLM returned an error/fallback string (our llm_client provides that), wrap it
    if isinstance(out, str) and out.startswith("[LLM ERROR]"):
        return [{
            "file": "unknown",
            "line": None,
            "category": "info",
            "severity": "low",
            "comment": "LLM unavailable or failed to aggregate findings. " + out,
            "suggestion": None
        }]

    # Try to parse the output as JSON (robustly)
    try:
        parsed = _extract_json_from_text(out)
        # Ensure it's a list of dict-like objects
        if isinstance(parsed, list):
            cleaned = []
            for item in parsed:
                if isinstance(item, dict):
                    cleaned.append(item)
                else:
                    # non-dict items -> convert to a dict wrapper
                    cleaned.append({
                        "file": getattr(item, "file", "unknown") if hasattr(item, "file") else "unknown",
                        "line": None,
                        "category": "info",
                        "severity": "low",
                        "comment": str(item),
                        "suggestion": None
                    })
            return cleaned
        elif isinstance(parsed, dict):
            # single dict -> wrap into list
            return [parsed]
    except Exception:
        # fall through to fallback handling below
        pass

    # Final fallback: try to interpret the LLM output as a human-readable list (best-effort)
    # If out contains multiple lines starting with '-', '*' or numbers, split them into entries
    try:
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        entries = []
        for ln in lines:
            # small heuristic: ignore lines that look like JSON fragments
            if ln.startswith('{') or ln.startswith('[') or ln.startswith('```'):
                continue
            entries.append({
                "file": "unknown",
                "line": None,
                "category": "info",
                "severity": "low",
                "comment": ln,
                "suggestion": None
            })
        if entries:
            return entries
    except Exception:
        pass

    # Ultimate fallback: return the whole raw output as a single info comment
    return [{
        "file": "unknown",
        "line": None,
        "category": "info",
        "severity": "low",
        "comment": out[:5000],  # truncate if extremely long
        "suggestion": None
    }]
