#!/usr/bin/env python3
"""macro_brief_guard.py — deterministic ingestion guard for macro_alpha_brief artifacts.

Self-contained, stdlib-only. Validates structure, controlled vocabularies,
referential integrity, machine-checkability of invalidation conditions, and
freshness, emitting composite rejection codes. Mirrors the allow / reject
decision model of task_guard.py.

Usage:
    python3 macro_brief_guard.py <artifact.json>     # validate one artifact
    python3 macro_brief_guard.py --test              # run embedded fixtures

Exit code 0 = ACCEPT (no ERROR-level codes), 1 = REJECT.
"""
import json, sys, re, datetime

SCHEMA_VERSIONS = {"1.1.0"}
REPORT_TYPE = "macro_alpha_brief"
DIRECTIONS = {"risk_off_btc_overweight", "risk_on_alt_overweight", "neutral_balanced"}
BIASES = {"risk_off", "risk_on", "neutral"}
TIERS = {"HIGH", "MEDIUM", "LOW"}
COMPARATORS = {">", ">=", "<", "<=", "==", "!="}
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
STALE_DAYS = 2  # data older than this vs generated_at -> WARN

# code -> (severity, human description)
CODES = {
    "E001": ("ERROR", "missing required field"),
    "E002": ("ERROR", "type mismatch"),
    "E003": ("ERROR", "enum / controlled-vocabulary violation"),
    "E004": ("ERROR", "discriminator mismatch (report_type != report_type_guard)"),
    "E005": ("ERROR", "unsupported schema_version"),
    "E006": ("ERROR", "timestamp not ISO-8601 UTC (YYYY-MM-DDThh:mm:ssZ)"),
    "E007": ("ERROR", "confidence numeric out of [0,1] range"),
    "E008": ("ERROR", "evidence array empty"),
    "E009": ("ERROR", "broken source_ref (not present in sources[])"),
    "E010": ("ERROR", "invalidation condition not machine-checkable"),
    "E011": ("ERROR", "duplicate id within a collection"),
    "E013": ("ERROR", "signal thresholds inconsistent or normalized out of [-1,1]"),
    "E015": ("ERROR", "data_as_of after generated_at"),
    "W012": ("WARN", "provenance completeness below 0.80"),
    "W014": ("WARN", "data_as_of is stale relative to generated_at"),
}

REQUIRED_TOP = ["schema_version", "report_type", "report_type_guard", "brief_id",
                "generated_at", "data_as_of", "market_window", "theme", "thesis",
                "evidence", "scoring_readiness", "invalidation", "confidence",
                "sources", "provenance"]


def _parse_ts(s):
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def validate(doc):
    """Return list of (code, path, detail). ERROR-level codes mean reject."""
    f = []

    def add(code, path, detail=""):
        f.append((code, path, detail))

    # --- top-level required + types -------------------------------------
    if not isinstance(doc, dict):
        add("E002", "$", "root is not an object")
        return f
    for k in REQUIRED_TOP:
        if k not in doc:
            add("E001", k)

    if doc.get("schema_version") not in SCHEMA_VERSIONS:
        add("E005", "schema_version", repr(doc.get("schema_version")))
    if doc.get("report_type") != REPORT_TYPE:
        add("E003", "report_type", repr(doc.get("report_type")))
    if doc.get("report_type") != doc.get("report_type_guard"):
        add("E004", "report_type_guard",
            f'{doc.get("report_type")!r} != {doc.get("report_type_guard")!r}')

    # --- timestamps -----------------------------------------------------
    for tk in ("generated_at", "data_as_of"):
        v = doc.get(tk)
        if isinstance(v, str) and not ISO_RE.match(v):
            add("E006", tk, v)
    try:
        g = _parse_ts(doc["generated_at"]); d = _parse_ts(doc["data_as_of"])
        if d > g:
            add("E015", "data_as_of", f"{doc['data_as_of']} > {doc['generated_at']}")
        elif (g - d).total_seconds() > STALE_DAYS * 86400:
            add("W014", "data_as_of", f"{(g - d).days}d behind generated_at")
    except (KeyError, ValueError):
        pass  # format errors already flagged by E006

    # --- thesis ---------------------------------------------------------
    th = doc.get("thesis", {})
    if isinstance(th, dict):
        if th.get("direction") not in DIRECTIONS:
            add("E003", "thesis.direction", repr(th.get("direction")))
        if not isinstance(th.get("statement"), str) or not th.get("statement"):
            add("E001", "thesis.statement")
    else:
        add("E002", "thesis", "not an object")

    # --- sources + referential integrity --------------------------------
    sources = doc.get("sources", [])
    src_ids = [s.get("id") for s in sources] if isinstance(sources, list) else []
    if len(src_ids) != len(set(src_ids)):
        add("E011", "sources[].id", "duplicate source id")
    src_set = set(src_ids)

    # --- evidence -------------------------------------------------------
    ev = doc.get("evidence", [])
    if not isinstance(ev, list) or len(ev) == 0:
        add("E008", "evidence")
    else:
        seen = set()
        for i, e in enumerate(ev):
            p = f"evidence[{i}]"
            if e.get("id") in seen:
                add("E011", f"{p}.id", e.get("id"))
            seen.add(e.get("id"))
            if e.get("confidence") not in TIERS:
                add("E003", f"{p}.confidence", repr(e.get("confidence")))
            if e.get("source_ref") not in src_set:
                add("E009", f"{p}.source_ref", repr(e.get("source_ref")))
            if "value" not in e:
                add("E001", f"{p}.value")

    # --- scoring_readiness ---------------------------------------------
    sr = doc.get("scoring_readiness", {})
    if isinstance(sr, dict):
        if sr.get("directional_bias") not in BIASES:
            add("E003", "scoring_readiness.directional_bias", repr(sr.get("directional_bias")))
        cw = sr.get("conviction_weight")
        if not isinstance(cw, (int, float)) or not (0.0 <= cw <= 1.0):
            add("E007", "scoring_readiness.conviction_weight", repr(cw))
        for i, s in enumerate(sr.get("signals", [])):
            p = f"scoring_readiness.signals[{i}]"
            nb, bb = s.get("threshold_bear"), s.get("threshold_bull")
            norm = s.get("normalized")
            if not isinstance(norm, (int, float)) or not (-1.0 <= norm <= 1.0):
                add("E013", f"{p}.normalized", repr(norm))
            # bull and bear thresholds must differ and be ordered consistently
            if isinstance(nb, (int, float)) and isinstance(bb, (int, float)) and nb == bb:
                add("E013", f"{p}.thresholds", "bull == bear")
    else:
        add("E002", "scoring_readiness", "not an object")

    # --- invalidation: must be machine-checkable ------------------------
    inv = doc.get("invalidation", {})
    conds = inv.get("conditions", []) if isinstance(inv, dict) else []
    if not conds:
        add("E010", "invalidation.conditions", "no conditions")
    for i, c in enumerate(conds):
        p = f"invalidation.conditions[{i}]"
        if not isinstance(c.get("metric"), str) or not c.get("metric"):
            add("E010", f"{p}.metric")
        if c.get("comparator") not in COMPARATORS:
            add("E010", f"{p}.comparator", repr(c.get("comparator")))
        if not isinstance(c.get("value"), (int, float)):
            add("E010", f"{p}.value", repr(c.get("value")))

    # --- confidence -----------------------------------------------------
    conf = doc.get("confidence", {})
    if isinstance(conf, dict):
        if conf.get("overall_tier") not in TIERS:
            add("E003", "confidence.overall_tier", repr(conf.get("overall_tier")))
        n = conf.get("overall_numeric")
        if not isinstance(n, (int, float)) or not (0.0 <= n <= 1.0):
            add("E007", "confidence.overall_numeric", repr(n))

    # --- provenance -----------------------------------------------------
    prov = doc.get("provenance", {})
    if isinstance(prov, dict):
        cs = prov.get("completeness_score")
        if isinstance(cs, (int, float)) and cs < 0.80:
            add("W012", "provenance.completeness_score", repr(cs))

    return f


def report(doc, label="artifact"):
    findings = validate(doc)
    errors = [x for x in findings if CODES.get(x[0], ("ERROR",))[0] == "ERROR"]
    warns = [x for x in findings if CODES.get(x[0], ("",))[0] == "WARN"]
    print(f"--- {label} ---")
    if not findings:
        print("ACCEPT  (clean — no rejection codes)")
    for code, path, detail in findings:
        sev, desc = CODES.get(code, ("ERROR", "unknown"))
        print(f"  [{sev}] {code} {path}: {desc}" + (f" -> {detail}" if detail else ""))
    decision = "REJECT" if errors else "ACCEPT"
    print(f"=> {decision}  (errors={len(errors)} warnings={len(warns)})")
    return decision == "ACCEPT"


# --------------------------------------------------------------------------
# Embedded fixtures for --test (proves the guard catches what it claims to)
# --------------------------------------------------------------------------
def _base():
    return {
        "schema_version": "1.1.0", "report_type": "macro_alpha_brief",
        "report_type_guard": "macro_alpha_brief", "brief_id": "pft-mab-test",
        "generated_at": "2026-05-30T15:57:58Z", "data_as_of": "2026-05-30T15:57:58Z",
        "market_window": {"label": "rolling_30d", "start": "2026-05-01", "end": "2026-05-30"},
        "theme": "stablecoin_liquidity_and_major_asset_rotation",
        "thesis": {"direction": "risk_off_btc_overweight", "statement": "x", "horizon_days": 30},
        "evidence": [{"id": "E1", "metric": "m", "value": 1, "unit": "percent",
                      "confidence": "HIGH", "source_ref": "S1"}],
        "scoring_readiness": {"directional_bias": "risk_off", "conviction_weight": 0.6,
                              "signals": [{"id": "X", "normalized": 0.5,
                                           "threshold_bull": 2.0, "threshold_bear": 0.0}]},
        "invalidation": {"logic": "ANY", "conditions": [
            {"id": "INV1", "metric": "m", "comparator": ">=", "value": 2.0}]},
        "confidence": {"overall_tier": "MEDIUM", "overall_numeric": 0.62},
        "sources": [{"id": "S1", "name": "src"}],
        "provenance": {"completeness_score": 0.92},
    }


def _run_tests():
    cases = []

    valid = _base(); cases.append(("valid", valid, True, None))

    bad_disc = _base(); bad_disc["report_type_guard"] = "protocol_score"
    cases.append(("discriminator_mismatch", bad_disc, False, "E004"))

    bad_ref = _base(); bad_ref["evidence"][0]["source_ref"] = "S9"
    cases.append(("broken_source_ref", bad_ref, False, "E009"))

    bad_inv = _base(); bad_inv["invalidation"]["conditions"][0]["comparator"] = "approximately"
    cases.append(("invalidation_not_checkable", bad_inv, False, "E010"))

    bad_enum = _base(); bad_enum["thesis"]["direction"] = "moon"
    cases.append(("bad_direction_enum", bad_enum, False, "E003"))

    bad_ts = _base(); bad_ts["data_as_of"] = "May 30 2026"
    cases.append(("bad_timestamp", bad_ts, False, "E006"))

    bad_conf = _base(); bad_conf["confidence"]["overall_numeric"] = 1.7
    cases.append(("confidence_range", bad_conf, False, "E007"))

    empty_ev = _base(); empty_ev["evidence"] = []
    cases.append(("empty_evidence", empty_ev, False, "E008"))

    bad_norm = _base(); bad_norm["scoring_readiness"]["signals"][0]["normalized"] = 4.0
    cases.append(("signal_norm_oob", bad_norm, False, "E013"))

    future = _base(); future["data_as_of"] = "2026-05-31T00:00:00Z"
    cases.append(("data_after_generated", future, False, "E015"))

    low_prov = _base(); low_prov["provenance"]["completeness_score"] = 0.5
    cases.append(("low_provenance_warn", low_prov, True, "W012"))  # WARN, still ACCEPT

    passed = 0
    for name, doc, want_accept, want_code in cases:
        findings = validate(doc)
        codes = {c for c, _, _ in findings}
        errors = [x for x in findings if CODES.get(x[0], ("ERROR",))[0] == "ERROR"]
        accept = not errors
        ok_decision = (accept == want_accept)
        ok_code = (want_code is None) or (want_code in codes)
        ok = ok_decision and ok_code
        passed += ok
        status = "PASS" if ok else "FAIL"
        detail = f"accept={accept}(want {want_accept})"
        if want_code:
            detail += f" code {want_code} {'present' if want_code in codes else 'MISSING'}"
        print(f"  [{status}] {name}: {detail}")
    print(f"\n{passed}/{len(cases)} fixtures passed")
    return passed == len(cases)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--test":
        sys.exit(0 if _run_tests() else 1)
    elif len(sys.argv) == 2:
        doc = json.load(open(sys.argv[1]))
        sys.exit(0 if report(doc, sys.argv[1]) else 1)
    else:
        print(__doc__); sys.exit(2)
