"""Strength of evidence, read from the quote itself (no LLM).

The IPCC states key findings as fact, or with a calibrated likelihood and/or confidence
term. Extracting them lets the interface show how strongly a source states something.
"""
import re

_LIKELIHOOD = re.compile(
    r"\b(exceptionally unlikely|extremely unlikely|very unlikely|unlikely|virtually certain|"
    r"extremely likely|very likely|more likely than not|about as likely as not|likely)\b", re.I)
_CONFIDENCE = re.compile(r"\b(very high|high|medium|low|very low) confidence\b", re.I)


def strength(quote: str) -> dict:
    lik, conf = _LIKELIHOOD.search(quote), _CONFIDENCE.search(quote)
    return {"likelihood": lik.group(1).lower() if lik else None,
            "confidence": conf.group(1).lower() if conf else None,
            "stated_as_fact": "unequivocal" in quote.lower()}
