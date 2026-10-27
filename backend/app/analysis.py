"""One email in, one verdict out: the rules first, then the bounded LLM (ADR-003, ADR-019).

The rules and the LLM look at the email independently; this module combines them.
The LLM adds only what the rules missed (a tactic or an injection attempt the phrase
lists did not find), so agreement is not counted twice. Its points are capped and
never subtract. Without an LLM answer the result is the rules' alone, marked partial
(ADR-005).
"""

from app import llm
from app.config import get_settings
from app.models import AiCheck, AnalyzeRequest, AnalyzeResponse, Manipulation, Reason
from app.scoring import score
from app.signals import language
from app.signals.base import Finding
from app.signals.engine import run_checks, sort_reasons, summarize, to_reasons
from app.verdict import verdict_for

RULE_INJECTION_IDS = {"ai_instructions", "ai_instructions_hidden"}

# Fixed wording (ADR-017) when a decisive finding lifts the score (ADR-010).
DECISIVE_NOTE = (
    "One of them is a trick no legitimate email uses, so this email is treated as malicious."
)


def llm_findings(
    verdict: llm.LlmVerdict, rule_tactics: list[Manipulation], rule_reasons: list[Reason]
) -> list[Finding]:
    # The model's own "not sure" is not evidence.
    if verdict.confidence == "low":
        return []
    findings = []
    missed = [tactic for tactic in verdict.manipulation if tactic not in rule_tactics]
    if missed:
        findings.append(Finding("llm_manipulation", tuple(missed)))
    if verdict.injection_attempt and not RULE_INJECTION_IDS & {r.id for r in rule_reasons}:
        findings.append(Finding("llm_ai_instructions"))
    return findings


def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    rule_reasons = run_checks(request)
    rule_tactics = language.labels(request)
    tactics = list(rule_tactics)

    verdict = llm.classify(request)
    llm_reasons: list[Reason] = []
    ai = AiCheck(ran=verdict is not None)
    if verdict:
        llm_reasons = [
            reason.model_copy(update={"source": "ai"})
            for reason in to_reasons(llm_findings(verdict, rule_tactics, rule_reasons))
        ]
        if verdict.confidence != "low":
            tactics += [tactic for tactic in verdict.manipulation if tactic not in tactics]
            ai = AiCheck(
                ran=True, tactics=verdict.manipulation, injection=verdict.injection_attempt
            )

    scored = score(rule_reasons, llm_reasons)
    reasons = sort_reasons(scored.reasons)
    summary = summarize(reasons)
    if scored.floored:
        summary += " " + DECISIVE_NOTE
    return AnalyzeResponse(
        score=scored.score,
        verdict=verdict_for(scored.score),
        summary=summary,
        reasons=reasons,
        manipulation=tactics,
        ai=ai,
        partial=verdict is None,
        mode=get_settings().mode,
    )
