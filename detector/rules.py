"""Rule-based red-flag detector.

Interface used by the web app:

    check(text) -> {"score": int, "indicator": "red_flags" | "no_flags",
                    "hits": [{"rule_id", "explanation", "matched_text", "start", "end"}]}

A match is ignored when a negation word ("never", "no", "do not", ...) appears in the
few words before it in the same sentence, so "we never charge a registration fee" is not flagged.
"""
import re
from dataclasses import dataclass

from markupsafe import Markup, escape


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: re.Pattern
    weight: int
    explanation: str
    negatable: bool = True


RULES = [
    Rule(
        "payment_fee",
        re.compile(r"\b(?:registration|security|training|joining|processing|onboarding|verification)\s+"
                   r"(?:fee|deposit|charge|amount)s?\b", re.I),
        3,
        "Asks for a fee or deposit.",
    ),
    Rule(
        "upfront_payment",
        re.compile(r"\bpay\s+(?:a\s+)?(?:small|nominal|minimal|one[- ]time)\s+(?:amount|fee|charges?)\b"
                   r"|\brefundable\s+(?:amount|fee)\b"
                   r"|\b(?:pay|deposit|invest)\s+(?:rs\.?|inr|₹)\s?\d[\d,]*", re.I),
        3,
        "Asks you to pay money before you start.",
    ),
    Rule(
        "off_platform_contact",
        re.compile(r"\b(?:wa|t)\.me/\S+|\b(?:whats\s?app|telegram)\b", re.I),
        2,
        "Moves the conversation to WhatsApp or Telegram channels.",
    ),
    Rule(
        "unrealistic_pay",
        re.compile(r"\bdaily\s+(?:payout|payment|income|earnings?)\b"
                   r"|(?:\brs\.?|\binr|₹)\s?\d[\d,]*(?:\s*/-)?\s*(?:per|a|/|every)\s*(?:day|task)\b"
                   r"|\bearn\s+(?:rs\.?|inr|₹)\s?\d[\d,]*\s*(?:daily|weekly)\b", re.I),
        2,
        "Promises fixed daily or per-task earnings, a common lure.",
    ),
    Rule(
        "get_rich_quick",
        re.compile(r"\b(?:unlimited\s+(?:income|earnings?|earning\s+potential)|be\s+your\s+own\s+boss"
                   r"|financial\s+freedom|easy\s+money|passive\s+income|earn\s+money\s+(?:from|at)\s+home)\b", re.I),
        2,
        "Promises unlimited or effortless income.",
    ),
    Rule(
        "id_documents",
        re.compile(r"\b(?:aadhaa?r|pan\s+(?:card|number|no)|social\s+security\s+number|ssn"
                   r"|passport\s+(?:copy|number|details))\b", re.I),
        2,
        "Asks for identity documents such as Aadhaar or PAN, which can be misused.",
    ),
    Rule(
        "bank_details",
        re.compile(r"\b(?:bank\s+(?:account|details|statement)|account\s+number|ifsc|upi\s+(?:id|pin)"
                   r"|atm\s+pin|cvv|debit\s+card|credit\s+card\s+(?:number|details))\b", re.I),
        2,
        "Asks for bank or card details.",
    ),
    Rule(
        "otp_request",
        re.compile(r"\b(?:otp|one[- ]time\s+password)\b", re.I),
        3,
        "Mentions an OTP, which can give someone access to your accounts.",
    ),
    Rule(
        "free_email",
        re.compile(r"\b[\w.+-]+@(?:gmail|yahoo|hotmail|outlook|rediffmail|ymail|aol)\.(?:com|co\.in|in)\b", re.I),
        2,
        "Gives a free email address (such as Gmail) instead of a company address.",
    ),
    Rule(
        "urgency",
        re.compile(r"\b(?:limited\s+(?:seats|slots|vacancies|openings|positions)|join\s+(?:today|immediately|now)"
                   r"|offer\s+(?:expires|valid\s+(?:till|until|only))|apply\s+(?:immediately|asap)|hurry"
                   r"|urgent(?:ly)?\s+(?:hiring|requirement|opening)"
                   r"|only\s+\d+\s+(?:seats|slots|positions|vacancies)\s+left)\b", re.I),
        1,
        "Pushes you to act quickly before you can check.",
    ),
    Rule(
        "task_scam",
        re.compile(r"\b(?:like\s+(?:and|&)\s+subscribe|(?:lik(?:e|ing)|rat(?:e|ing)|review(?:ing)?)\s+(?:youtube\s+)?"
                   r"(?:videos?|products?|hotels?|restaurants?|movies?)|(?:online|simple|prepaid|merchant)\s+tasks?"
                   r"|task[- ]based\s+(?:job|work)|youtube\s+likes?)\b", re.I),
        3,
        "Describes paid tasks such as liking videos or rating products, a known scam script.",
    ),
    Rule(
        "no_interview",
        re.compile(r"\b(?:no|without(?:\s+any)?)\s+interviews?\b|\bdirect\s+joining\b", re.I),
        2,
        "Says there is no interview, which genuine employers rarely skip.",
        negatable=False,
    ),
    Rule(
        "no_experience",
        re.compile(r"\bno\s+(?:prior\s+)?(?:experience|qualifications?|skills?)\s+(?:is\s+|are\s+)?"
                   r"(?:needed|required|necessary)\b", re.I),
        1,
        "Says no experience or qualification is needed.",
        negatable=False,
    ),
    Rule(
        "typing_jobs",
        re.compile(r"\b(?:copy[- ]paste\s+(?:work|jobs?)|form\s+filling|typing\s+(?:work|jobs?)|sms\s+sending"
                   r"|ad\s+posting\s+(?:work|jobs?)|captcha\s+(?:entry|typing|work))\b", re.I),
        2,
        "Offers simple home jobs such as copy-paste or form filling, which scams often use.",
    ),
    Rule(
        "money_transfer",
        re.compile(r"\b(?:(?:receive|transfer|forward|process)\s+(?:funds|payments|money)\s+on\s+behalf"
                   r"|western\s+union|moneygram|money\s+transfer\s+(?:agent|officer)"
                   r"|payment\s+processing\s+(?:agent|representative)|financial\s+agent)\b", re.I),
        3,
        "Involves receiving or forwarding money, which can make you part of a fraud.",
    ),
    Rule(
        "guaranteed_job",
        re.compile(r"\b(?:100\s?%\s+(?:job|placement)|guaranteed\s+(?:job|placement|income|earnings?|selection|salary)"
                   r"|job\s+guarantee)\b", re.I),
        2,
        "Guarantees a job or income, which no genuine employer can promise.",
    ),
    Rule(
        "wallet_recharge",
        re.compile(r"\b(?:recharge\s+(?:your\s+)?(?:account|wallet)|withdraw(?:al)?\s+(?:your\s+)?"
                   r"(?:commission|earnings|profit)|crypto(?:currency)?\s+(?:wallet|trading|investment)|usdt|bitcoin)\b",
                   re.I),
        3,
        "Talks about topping up a wallet or withdrawing commission, a task-scam pattern.",
    ),
    Rule(
        "unnamed_employer",
        re.compile(r"\b(?:reputed\s+(?:mnc|company|firm|organi[sz]ation)s?"
                   r"|(?:company|client)\s+name\s+(?:is\s+)?(?:confidential|not\s+disclosed|will\s+be\s+(?:disclosed|shared)))\b",
                   re.I),
        1,
        "Hides the employer's name, so the posting cannot be verified.",
    ),
]
EXPLANATIONS = {r.id: r.explanation for r in RULES}
THRESHOLD = 1
NEGATIONS = {"no", "not", "never", "nor", "without", "dont", "doesnt", "wont", "cannot", "zero"}
NEGATION_WINDOW = 5


def negated(text, start):
    """True if a negation word is among the NEGATION_WINDOW words before start, in the same sentence."""
    words = re.split(r"[.!?\n]", text[:start])[-1].split()[-NEGATION_WINDOW:]
    return any(w.strip(",;:()\"").replace("'", "").replace("’", "").lower() in NEGATIONS for w in words)


def check(text, handle_negation=True):
    hits = [
        {"rule_id": r.id, "explanation": r.explanation, "matched_text": m.group(0),
         "start": m.start(), "end": m.end()}
        for r in RULES
        for m in r.pattern.finditer(text)
        if not (handle_negation and r.negatable and negated(text, m.start()))
    ]
    fired = {h["rule_id"] for h in hits}
    score = sum(r.weight for r in RULES if r.id in fired)
    return {"score": score, "indicator": "red_flags" if score >= THRESHOLD else "no_flags", "hits": hits}


def highlight(text, spans):
    """Return text as safe HTML with each (start, end) span wrapped in <mark>.

    The text is escaped before tags are added, so pasted HTML is never rendered.
    Overlapping spans are merged.
    """
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    parts, pos = [], 0
    for start, end in merged:
        parts += [escape(text[pos:start]), Markup("<mark>"), escape(text[start:end]), Markup("</mark>")]
        pos = end
    parts.append(escape(text[pos:]))
    return Markup("").join(parts)
