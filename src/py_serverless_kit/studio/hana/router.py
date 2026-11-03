"""Does this message need the docs? Decided before studio searches them for the model.

Studio used to run ``search_docs`` before every answer, so even "hi" was answered from three docs excerpts. The
router decides first:

1. Rules (instant): greetings, thanks, goodbyes and "who are you" need no docs; anything that names pskit, a cloud,
   a config key, a command or asks how/why/what about a feature does.
2. Only when the rules cannot tell: one tiny classification call to the model (no tools, a few tokens). If that call
   fails or answers something unexpected, studio searches (searching when unsure is the safe side).
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from .knowledge import words

# The whole message is small talk (punctuation, emoji and "hana" around it allowed)
_SMALL_TALK = re.compile(
    r"^\W*(?:(?:hi+|hii+|hey+|hello+|helo|hiya|yo|sup|namaste|salam|good\s+(?:morning|afternoon|evening|night|day)|"
    r"thanks?(?:\s+(?:you|a\s+lot|so\s+much))*|thank\s+you(?:\s+(?:so\s+much|very\s+much))?|thx|ty|cheers|"
    r"bye+|goodbye|see\s+you|cya|good\s+job|nice|great|awesome|cool|perfect|ok(?:ay)?|k|fine|got\s+it|"
    r"how\s+are\s+you(?:\s+doing)?|how'?s\s+it\s+going|what'?s\s+up|who\s+are\s+you|what\s+is\s+your\s+name|"
    r"what'?s\s+your\s+name|are\s+you\s+there)"
    r"(?:\s+(?:there|hana|buddy|friend|again|today))*[\s\W]*)+$", re.I)
# Short affirmations that continue the previous question ("yes", "do it"): they keep the previous topic's search
_CONTINUE = re.compile(r"^\W*(?:yes|yeah|yep|y|sure|ok(?:ay)?|k|go\s+ahead|do\s+it|continue|proceed|next|more)\W*$",
                       re.I)
# Signs the message is about pskit: then the docs are searched without asking the model
_TECH = re.compile(
    r"\b(pskit|studio|hana|deploy\w*|undeploy|destroy|remove|terraform|tofu|yml|yaml|config\w*|function\w*|handler\w*|"
    r"trigger\w*|http|api|route\w*|cors|schedule\w*|cron|queue\w*|bucket\w*|storage|database|db|postgres\w*|mysql|redis|"
    r"mongo\w*|sql|workflow\w*|step\s*functions?|orchestrat\w*|stage\w*|provider\w*|region\w*|aws|amazon|lambda|azure|"
    r"gcp|google|cloud|alibaba|tencent|huawei|oracle|ibm|digitalocean|cloudflare|onprem|on[-\s]?prem\w*|server\w*|vm|"
    r"cluster\w*|load\s*balancer\w*|replica\w*|docker|kubernetes|k8s|ssh|install\w*|env\w*|variable\w*|secret\w*|"
    r"package\w*|zip|artifact\w*|bundle|layer\w*|runtime|python|pip|requirements|log\w*|metric\w*|dashboard|error\w*|"
    r"fail\w*|bug|timeout|memory|invoke|event\w*|webhook\w*|auth\w*|iam|role\w*|permission\w*|domain\w*|ssl|tls|"
    r"cert\w*|scal\w*|cost\w*|price|pricing|validate|validation|command\w*|cli)\b", re.I)
_QUESTION = re.compile(r"\?|^\W*(how|why|what|which|where|when|can|could|does|do|is|are|should|will|explain|help)\b",
                       re.I)

CLASSIFY_PROMPT = (
    "You sort chat messages for Hana, the assistant of the pskit serverless deployment tool. Answer with one word: "
    "DOCS if answering needs facts from the pskit documentation (features, configuration, commands, clouds, errors), "
    "CHAT if it is small talk or needs no pskit facts.")


def classify(model: Any, text: str) -> Optional[bool]:
    """Ask the model DOCS or CHAT; ``None`` when it fails or answers neither."""
    try:
        out = model.chat([{"role": "system", "content": CLASSIFY_PROMPT},
                          {"role": "user", "content": f"Message: {text[:400]}\nAnswer DOCS or CHAT."}], [], max_tokens=4)
    except Exception:  # noqa: BLE001 - any failure here means "search to be safe"
        return None
    answer = str(out.get("content") or "").strip().upper()
    if out.get("tool_calls") or not answer:
        return None
    if answer.startswith("DOCS"):
        return True
    if answer.startswith("CHAT"):
        return False
    return None


def needs_docs(text: str, history: List[Dict[str, Any]],
               ask: Optional[Callable[[str], Optional[bool]]] = None) -> Tuple[bool, str]:
    """``(search the docs?, why)``. ``ask`` is the model classifier, called only when the rules cannot tell."""
    message = " ".join(text.split())
    if not words(message):
        return False, "nothing to search"
    if _CONTINUE.match(message):
        previous = any(m.get("role") == "user" for m in history)
        return previous, ("a short reply: searched with the previous question" if previous else "a short reply")
    if _SMALL_TALK.match(message):
        return False, "small talk"
    if _TECH.search(message):
        return True, "asks about pskit"
    if ask is not None:
        verdict = ask(message)
        if verdict is not None:
            return verdict, "the model says it needs the docs" if verdict else "the model says it needs no docs"
    if _QUESTION.search(message) or len(words(message)) > 6:
        return True, "a question the rules could not place: searched to be safe"
    return False, "a short message with no pskit topic"
