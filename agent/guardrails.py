"""Output guardrail for §3.1 "Guardrails (input & output)": keep secrets out of files the agents write.

If a file the agents produced contains something that looks like a real credential (an API key, a private key), it is
replaced with a placeholder and reported, so it never lands in a user's repository or download. Only provider-specific,
high-confidence patterns are matched (a generic "password = ..." rule would rewrite ordinary test fixtures). A secret that
was already in the file before this run is left alone: it is the user's own content, not something the agent introduced.
"""
import re

_PATTERNS = [
    ("private key", re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----.*?-----END (?:[A-Z]+ )*PRIVATE KEY-----", re.S),
     "YOUR_PRIVATE_KEY_HERE"),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "YOUR_AWS_ACCESS_KEY_ID_HERE"),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), "YOUR_GITHUB_TOKEN_HERE"),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "YOUR_GOOGLE_API_KEY_HERE"),
    ("Groq API key", re.compile(r"\bgsk_[A-Za-z0-9]{40,}\b"), "YOUR_GROQ_API_KEY_HERE"),
    ("OpenAI API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}"), "YOUR_OPENAI_API_KEY_HERE"),
    ("Stripe secret key", re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{20,}\b"), "YOUR_STRIPE_SECRET_KEY_HERE"),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"), "YOUR_SLACK_TOKEN_HERE"),
]


def redact_new_secrets(content: str, previous: str = "") -> tuple[str, list[str]]:
    """Return (content with newly introduced secrets replaced, the kinds of secret replaced). `previous` is what the file
    held before this run; matches already present there are kept."""
    found: list[str] = []
    for kind, pattern, placeholder in _PATTERNS:
        def replace(match, kind=kind, placeholder=placeholder):
            if previous and match.group(0) in previous:
                return match.group(0)
            found.append(kind)
            return placeholder
        content = pattern.sub(replace, content)
    return content, found


def describe_redactions(redactions: list) -> str:
    """One sentence for the user's reply, e.g. after an edit. `redactions` = [{"file": ..., "kinds": [...]}, ...]."""
    if not redactions:
        return ""
    count = sum(len(r["kinds"]) for r in redactions)
    where = ", ".join(f"{r['file']} ({', '.join(sorted(set(r['kinds'])))})" for r in redactions)
    return (f"🔒 Replaced {count} possible secret{'s' if count != 1 else ''} with a placeholder in {where}. "
            "Keep real keys in environment variables, not in code.")
