"""Extractors for Balance of Payments, WSS, MPC minutes and Sectoral Deployment of Bank Credit (prose part).

Same contract as auctions.py: (soup, ctx) -> (fields, rows) [BoP also returns prior_year via fields['_prior_year']].
Anything the page does not publish is simply left out (never estimated); items that need a human or the
Claude API fallback to finish are listed under fields['needs_review'].
"""
from __future__ import annotations

import re

from .common import ExtractionError, body_node, body_text, clean, grid, leaf_tables, num, parse_date


# ----------------------------------------------------------------------------- Balance of Payments
BOP_LABELS = [
    (r"^A\. Current Account", "current_account_balance"),
    (r"^A\.1 Merchandise", "trade_balance"),
    (r"^A\.2 Services", "net_services"),
    (r"^A\.3 Transfers", "net_transfers"),
    (r"^A\.4 Income", "net_income"),
    (r"^B\. Capital Account", "capital_account_balance"),
    (r"^B\.1 Foreign Direct", "fdi_net"),
    (r"^B\.2 Foreign Portfolio", "fpi_net"),
    (r"^B\.3 External Commercial", "ecb_net"),
    (r"^B\.4 Short-term", "short_term_credit_net"),
    (r"^B\.5 Banking Capital", "banking_capital_net"),
    (r"^of which: NRI", "nri_deposits_net"),
    (r"^B\.6 Other Capital", "other_capital_net"),
    (r"^C\. Overall Balance", "overall_balance"),
    (r"^D\. Monetary Movements", "monetary_movements"),   # published sign: '-' = increase in reserves
]


def _period(cell: str) -> str:
    return re.sub(r"\s+(PR|P|R)$", "", clean(cell))


def bop(soup, ctx):
    table = next((t for t in leaf_tables(body_node(soup))
                  if any(r and r[0] == "Item" for r in grid(t))), None)
    if table is None:
        raise ExtractionError("BoP table not found")
    rows = grid(table)
    hi = next(i for i, r in enumerate(rows) if r[0] == "Item")
    header = rows[hi]
    if len(header) != 5:
        raise ExtractionError(f"unexpected BoP header: {header}")
    # columns: [item, same period last year, this period, year-to-date last year, year-to-date this year]
    fields = {"period": _period(header[2]), "ytd_period": _period(header[4])}
    prior = {}
    section = None
    for r in rows[hi + 1:]:
        if len(r) != 5:
            continue
        name = next((n for rx, n in BOP_LABELS if re.search(rx, r[0])), None)
        if r[0].startswith("A.1 "):
            section = "merchandise"
        elif r[0].startswith("A.2 "):
            section = "services"
        elif re.match(r"^(A\.3|A\.4|B\.|C\.|D\.)", r[0]):
            section = None
        if name is None and section and re.match(r"^[ab]\. (Exports|Imports)", r[0]):
            name = f"{section}_{'exports' if 'Exports' in r[0] else 'imports'}"
        if name is None:
            continue
        for key, cur, prev in ((name, r[2], r[1]), (f"ytd_{name}", r[4], r[3])):
            fields[key] = num(cur)
            prior[key] = num(prev)
    if "current_account_balance" not in fields:
        raise ExtractionError("current account row not found in BoP table")
    fields["_prior_year"] = prior
    return fields, []


# ----------------------------------------------------------------------------- Weekly Statistical Supplement
# (table title regex, [(row label regex, field name, index into the row's value cells)])
WSS_TABLES = [
    (r"Foreign Exchange Reserves", [
        (r"^1 Total Reserves", "forex_reserves_total_inr_cr", 0),
        (r"^1 Total Reserves", "forex_reserves_total_usd_mn", 1),
        (r"^1\.1 Foreign Currency Assets", "forex_fca_usd_mn", 1),
        (r"^1\.2 Gold", "forex_gold_usd_mn", 1),
        (r"^1\.3 SDRs", "forex_sdrs_usd_mn", 1),
        (r"^1\.4 Reserve Position", "forex_imf_position_usd_mn", 1)]),
    (r"Scheduled Commercial Banks - Business in India", [
        (r"^2\.1 Aggregate Deposits", "aggregate_deposits", 0),
        (r"^2\.1a Growth", "aggregate_deposits_yoy_pct", -1),
        (r"^2\.1\.1 Demand", "demand_deposits", 0),
        (r"^2\.1\.2 Time", "time_deposits", 0),
        (r"^7 Bank Credit", "bank_credit", 0),
        (r"^7\.1a Growth", "bank_credit_yoy_pct", -1),
        (r"^7a\.2 Non-food", "non_food_credit", 0)]),
    (r"Money Stock", [
        (r"^M3$", "m3", 1),
        (r"^M3$", "m3_yoy_pct", -1),
        (r"^1\.1 Currency with the Public", "currency_with_public", 1),
        (r"^1\.1 Currency with the Public", "currency_with_public_yoy_pct", -1)]),
    (r"Reserve Bank of India - Liabilities and Assets", [
        (r"^4\.2 State Governments", "rbi_loans_to_state_govts", 2)]),
]


def wss(soup, ctx):
    """Extract whichever of the mapped series are present (the press-page WSS is an extract: it has
    forex reserves, aggregate deposits, bank credit, M3 and currency with the public, but not reserve
    money or SLR investments)."""
    fields = {}
    for table in leaf_tables(body_node(soup)):
        rows = grid(table)
        title = rows[0][0] if rows else ""
        for title_rx, mapping in WSS_TABLES:
            if not re.search(title_rx, title, re.I):
                continue
            for r in rows:
                for row_rx, name, idx in mapping:
                    vals = r[1:]
                    if re.search(row_rx, r[0]) and vals and name not in fields:
                        try:
                            v = num(vals[idx])
                        except IndexError:
                            v = None
                        if v is not None:
                            fields[name] = v
            if "Foreign Exchange" in title:
                m = re.search(r"As on ([A-Za-z]+ \d{1,2}, \d{4})", " ".join(" ".join(r) for r in rows[:3]))
                if m:
                    fields["forex_as_on"] = parse_date(m.group(1)).isoformat()
            if "Scheduled Commercial Banks" in title:
                m = re.search(r"as on ([A-Za-z]+\.? \d{1,2}, \d{4})", " ".join(" ".join(r) for r in rows[:3]))
                if m:
                    fields["scb_as_on"] = parse_date(m.group(1)).isoformat()
    if not any(isinstance(v, float) for v in fields.values()):
        raise ExtractionError("no WSS series found")
    return fields, []


# ----------------------------------------------------------------------------- MPC minutes
_VERBS = {"increase": "hike", "raise": "hike", "hike": "hike", "keep": "hold", "maintain": "hold",
          "retain": "hold", "reduce": "cut", "decrease": "cut", "cut": "cut", "lower": "cut"}


def _projection(text: str, subject_rx: str):
    m = re.search(subject_rx + r"(?: for (\d{4}-\d{2}))?\s+is\s+(?:now\s+|also\s+)?projected\s+(?:at|to be)\s+(\d+(?:\.\d+)?)\s+per cent",
                  text, re.I)
    if not m:
        return None, None
    period = m.group(1)
    if period is None:      # wording "... projected to be 5.2 per cent for 2026-27"
        after = re.match(r"\s*for (\d{4}-\d{2})", text[m.end():m.end() + 25])
        period = after.group(1) if after else None
    return float(m.group(2)), period


def mpc_minutes(soup, ctx):
    text = body_text(soup)
    review: list[str] = []
    m = re.search(r"the MPC voted\s.*?(\d+(?:\.\d+)?)\s+per cent", text)
    if not m:
        raise ExtractionError("policy decision sentence ('the MPC voted ...') not found")
    sentence = m.group(0)
    verb = next((v for v in re.findall(r"\b(increase|raise|hike|keep|maintain|retain|reduce|decrease|cut|lower)\b", sentence)), None)
    if verb is None:
        raise ExtractionError(f"cannot read the decision from: {sentence[:120]}")
    decision = _VERBS[verb]
    bps = re.search(r"by\s+(\d+)\s*(?:bps|basis points)", sentence)
    change = int(bps.group(1)) if bps else 0
    change = {"hike": change, "cut": -change, "hold": 0}[decision]
    stance = re.search(r"MPC also decided to (?:change the stance to|continue with the|maintain the|retain the|shift the stance to)\s+"
                       r"([A-Za-z ]+?)(?:\s+stance)?\s*\.", text)
    infl, infl_p = _projection(text, r"CPI inflation")
    growth, growth_p = _projection(text, r"real GDP growth")
    # a projection with no stated financial year may be a quarterly figure: do not record it as the headline
    if infl is not None and infl_p is None:
        infl = None
    if growth is not None and growth_p is None:
        growth = None
    if infl is None or growth is None:
        review.append("full-year inflation and/or growth projection not found by the rules")
    unanimous = bool(re.search(r"voted unanimously", sentence))

    # votes: table of Member | Yes/No (Yes = voted for the resolution)
    votes = []
    for t in leaf_tables(body_node(soup)):
        g = grid(t)
        if g and [c.lower() for c in g[0][:2]] == ["member", "vote"]:
            votes = [(r[0], r[1]) for r in g[1:] if len(r) >= 2]
            break
    if not votes:
        raise ExtractionError("vote table not found")
    statements = {}
    for sm in re.finditer(r"Statement by ([A-Z][^\d]{3,70}?)\s+\d{1,3}\.\s+(.{0,420})", text):
        statements[sm.group(1).strip()] = sm.group(2).strip()
    rows = []
    for name, v in votes:
        yes = v.strip().lower() == "yes"
        last = name.split()[-1].lower()
        excerpt = next((s for n, s in statements.items() if last in n.lower()), "")
        if not yes:
            review.append(f"{name} voted '{v}': direction and size of the dissent need reading from the statement")
        rows.append({"key": name, "vote": decision if yes else "dissent",
                     "vote_bps": abs(change) if yes else None, "rationale": excerpt})
    fields = {"decision": decision, "repo_rate": float(m.group(1)), "repo_change_bps": change,
              "stance": clean(stance.group(1)).lower() if stance else None,
              "inflation_projection": infl, "inflation_projection_period": infl_p,
              "growth_projection": growth, "growth_projection_period": growth_p,
              "unanimous": unanimous}
    if review:
        fields["needs_review"] = review
    return fields, rows


# ----------------------------------------------------------------------------- Sectoral credit (prose)
CREDIT_SECTORS = [
    ("Non-food credit", r"non-food bank credit"),
    ("Agriculture", r"Credit to agriculture"),
    ("Industry", r"Credit to industry"),
    ("Services", r"Credit to services"),
    ("Personal loans", r"Credit to personal loans"),
]


def sectoral_credit_text(soup, ctx):
    """Headline sectors from the page's own text: y-o-y growth and the prior-year growth it states."""
    text = body_text(soup)
    rows = []
    for name, rx in CREDIT_SECTORS:
        hit = re.search(rx, text, re.I if name == "Non-food credit" else 0)
        if hit is None:
            continue
        # the clause that starts at the sector phrase and ends at the next sentence start
        s = re.split(r"\.\s+(?=[A-Z\u2018\u201c])", text[hit.start():hit.start() + 500])[0]
        pcts = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s+per cent", s)]
        if not pcts:
            continue
        rows.append({"key": name, "yoy_growth_pct": pcts[0],
                     "prior_year_yoy_growth_pct": pcts[1] if len(pcts) > 1 else None})
    month = re.search(r"for the month of ([A-Za-z]+ \d{4})", text)
    fields = {"month": month.group(1) if month else None}
    xlsx = next((a["href"] for a in soup.find_all("a", href=True) if a["href"].lower().endswith((".xlsx", ".xls"))), None)
    fields["statements_file_url"] = xlsx
    if len(rows) < len(CREDIT_SECTORS):
        found = {r["key"] for r in rows}
        fields["needs_review"] = ["sector(s) not found in the text: "
                                  + ", ".join(n for n, _ in CREDIT_SECTORS if n not in found)]
    if not rows:
        raise ExtractionError("no sector growth figures found in the text")
    return fields, rows