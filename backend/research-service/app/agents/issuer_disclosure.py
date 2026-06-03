from __future__ import annotations

from collections.abc import Mapping
from typing import Any

FOREIGN_DISCLOSURE_NOTE = (
    "ADR/foreign issuer disclosure can have limited SEC narrative coverage; "
    "structured market metrics and company profile facts are primary evidence."
)


def issuer_type_from_facts(facts: Mapping[str, Any]) -> str:
    issuer_type = _optional_str(facts.get("issuer_type") or facts.get("issuerType"))
    if issuer_type:
        return issuer_type
    security_text = " ".join(
        value
        for value in [
            _optional_str(facts.get("market_security_type") or facts.get("marketSecurityType")),
            _optional_str(facts.get("security_type") or facts.get("securityType")),
            _optional_str(facts.get("market_type_display") or facts.get("marketTypeDisplay")),
            _optional_str(facts.get("market_quote_type") or facts.get("marketQuoteType")),
            _optional_str(facts.get("company_name") or facts.get("companyName")),
        ]
        if value
    ).lower()
    if (
        "adr" in security_text
        or "american depositary" in security_text
        or "depositary receipt" in security_text
    ):
        return "adr"
    country = _optional_str(facts.get("market_country") or facts.get("marketCountry"))
    if country and country.strip().lower() not in {"united states", "usa", "us", "u.s.", "u.s.a."}:
        return "foreign_issuer"
    return "unknown"


def disclosure_profile_from_facts(facts: Mapping[str, Any]) -> str | None:
    return _optional_str(facts.get("disclosure_profile") or facts.get("disclosureProfile"))


def disclosure_note_from_facts(facts: Mapping[str, Any]) -> str | None:
    return _optional_str(facts.get("disclosure_note") or facts.get("disclosureNote"))


def has_foreign_issuer_metric_policy(facts: Mapping[str, Any]) -> bool:
    issuer_type = issuer_type_from_facts(facts)
    return issuer_type in {"adr", "foreign_issuer"} and has_structured_market_evidence(
        facts
    )


def has_structured_market_evidence(facts: Mapping[str, Any]) -> bool:
    metrics = facts.get("metrics")
    if isinstance(metrics, list) and any(isinstance(metric, Mapping) for metric in metrics):
        return True
    return bool(
        _optional_str(facts.get("business_summary"))
        or _optional_str(facts.get("businessSummary"))
        or _optional_str(facts.get("market_business_summary"))
        or _optional_str(facts.get("marketBusinessSummary"))
    )


def foreign_issuer_metadata(facts: Mapping[str, Any]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    issuer_type = issuer_type_from_facts(facts)
    if issuer_type != "unknown":
        metadata["issuer_type"] = issuer_type
    disclosure_profile = disclosure_profile_from_facts(facts)
    if disclosure_profile:
        metadata["disclosure_profile"] = disclosure_profile
    disclosure_note = disclosure_note_from_facts(facts)
    if disclosure_note:
        metadata["disclosure_note"] = disclosure_note
    elif has_foreign_issuer_metric_policy(facts):
        metadata["disclosure_note"] = FOREIGN_DISCLOSURE_NOTE
    return metadata


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
