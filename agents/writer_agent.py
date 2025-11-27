from typing import List, Any
from .llm_client import call_openai
import json

def _stringify_item(item: Any) -> str:
    
    if isinstance(item, (dict, list)):
        try:
            return json.dumps(item, indent=2, ensure_ascii=False)
        except Exception:
            return str(item)
    return str(item)

def _extract_json_from_text(text: str) -> Any:
  
    try:
        return json.loads(text)
    except Exception:
        pass

    s = text
    start = s.find('[')
    end = s.rfind(']')
    if start != -1 and end != -1 and end > start:
        candidate = s[start:end+1]
        try:
            return json.loads(candidate)
        except Exception:
            pass

    start = s.find('{')
    end = s.rfind('}')
    if start != -1 and end != -1 and end > start:
        candidate = s[start:end+1]
        try:
            return json.loads(candidate)
        except Exception:
            pass

    raise ValueError("No JSON found in text")

def writer_agent(collected_findings: List[Any]) -> List[dict]:
    
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

    if isinstance(out, str) and out.startswith("[LLM ERROR]"):
        return [{
            "file": "unknown",
            "line": None,
            "category": "info",
            "severity": "low",
            "comment": "LLM unavailable or failed to aggregate findings. " + out,
            "suggestion": None
        }]

    try:
        parsed = _extract_json_from_text(out)
        if isinstance(parsed, list):
            cleaned = []
            for item in parsed:
                if isinstance(item, dict):
                    cleaned.append(item)
                else:
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
            return [parsed]
    except Exception:
        pass
    
    try:
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        entries = []
        for ln in lines:
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

    return [{
        "file": "unknown",
        "line": None,
        "category": "info",
        "severity": "low",
        "comment": out[:5000],
        "suggestion": None
    }]
