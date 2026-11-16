import json
from pathlib import Path

import pytest
import requests

from rbi_tracker.fetch.classify import default_classifier
from rbi_tracker.fetch.discover import discover_new
from rbi_tracker.fetch.listing import FetchError, ParseError, fetch_listing, parse_listing
from rbi_tracker.paths import load_yaml
from rbi_tracker.store.records import PressReleaseStore

# (title, expected item_id). Titles marked [live] were seen on the live RBI page in Nov 2026;
# [older] are wordings from earlier RBI releases not yet seen live.
CASES = [
    # --- CG ---
    ("Auction of Government of India Dated Securities", "cg_announcement"),                    # [live]
    ("Auction of Government of India Dated Security", "cg_announcement"),                      # [live]
    ("Government Stock - Full Auction Results", "cg_result"),                                  # [live]
    ("Government Stock - Auction Results: Cut-off", None),                                     # [live] deliberately not tracked
    # --- SG: must not be mistaken for CG although the titles share words ---
    ("Auction of State Government Securities", "sg_announcement"),                             # [live]
    ("State Government Securities - Full Auction Result", "sg_result"),                        # [live]
    # --- T-Bill ---
    ("Auction of 91-Day, 182-Day and 364-Day Treasury Bills", "tbill_announcement"),           # [live]
    ("Treasury Bills: Full Auction Result", "tbill_result"),                                   # [live]
    ("91-Day, 182-Day and 364-Day T-Bill Auction Result: Cut-off", None),                      # [live]
    # --- VRR vs VRRR must never cross-classify ---
    ("RBI to conduct 2-day Variable Rate Reverse Repo (VRRR) auction under LAF on November 17, 2026", "vrrr_announcement"),
    ("Result of the 3-day Variable Rate Reverse Repo (VRRR) auction held on November 13, 2026", "vrrr_result"),
    ("Result of the Overnight Variable Rate Reverse Repo (VRRR) auction held on November 12, 2026", "vrrr_result"),
    ("RBI to conduct 4-day Variable Rate Repo (VRR) auction under LAF on November 10, 2026", "vrr_announcement"),
    ("Result of the 4-day Variable Rate Repo (VRR) auction held on November 09, 2026", "vrr_result"),
    # --- OMO [older wording] ---
    ("RBI announces OMO Purchase of Government of India Securities", "omo_announcement"),
    ("Result of OMO Purchase auction held on March 25, 2025", "omo_result"),
    # --- publications ---
    ("Developments in India\u2019s Balance of Payments for the Month of September 2026", "bop"),    # [live]
    ("Reserve Bank of India \u2013 Bulletin Weekly Statistical Supplement \u2013 Extract", "wss"),  # [live]
    ("Minutes of the Monetary Policy Committee Meeting", "mpc_minutes"),                       # [older]
    ("Sectoral Deployment of Bank Credit \u2013 September 2026", "sectoral_credit"),           # [unverified]
    # --- look-alikes that are NOT tracked ---
    ("Result: Conversion/Switch Auction of Government of India Securities", None),             # [live]
    ("Conversion/Switch of Government of India Securities", None),                             # [live]
    ("Result of Underwriting Auction conducted on November 13, 2026", None),                   # [live]
    ("Underwriting Auction for sale of Government Security for \u20b934,000 crore on November 13, 2026", None),
    ("Money Market Operations as on November 15, 2026", None),                                 # [live]
    ("Scheduled Banks\u2019 Statement of Position in India as on October 31, 2026", None),     # [live]
]


@pytest.mark.parametrize("title,expected", CASES)
def test_classification(title, expected):
    assert default_classifier().classify(title) == expected


def test_announcement_and_result_never_share_an_item_type():
    clf = default_classifier()
    for fam, ann, res in [
        ("cg", "Auction of Government of India Dated Securities", "Government Stock - Full Auction Results"),
        ("tbill", "Auction of 91-Day, 182-Day and 364-Day Treasury Bills", "Treasury Bills: Full Auction Result"),
        ("vrrr", "RBI to conduct 2-day Variable Rate Reverse Repo (VRRR) auction under LAF on November 17, 2026",
         "Result of the 3-day Variable Rate Reverse Repo (VRRR) auction held on November 13, 2026"),
    ]:
        assert clf.classify(ann) == f"{fam}_announcement"
        assert clf.classify(res) == f"{fam}_result"


def test_every_rule_targets_a_real_item_and_every_press_item_has_a_rule():
    items = {i["id"]: i for i in load_yaml("items.yaml")["items"]}
    rule_ids = [r["item_id"] for r in load_yaml("classifier.yaml")["rules"]]
    assert set(rule_ids) <= set(items)
    press = {i for i, v in items.items() if v["source"] == "press_release"}
    assert press == set(rule_ids)


# ---------------- listing parser ----------------
def _row(title, prid):
    return (f'<tr><td><a class="link2" href="BS_PressReleaseDisplay.aspx?prid={prid}">{title}</a></td>'
            f'<td nowrap colspan="2"><a id="APDF_PR{prid}" target="_blank" href="https://rbidocs.rbi.org.in/rdocs/PressRelease/PDFs/PR{prid}.PDF">'
            f'<img alt="PDF" src="x.gif"></a><span id="SPDF_PR{prid}" aria-hidden="true">280 kb</span></td></tr>')


def _header(text):
    return f'<tr><td class="tableheader" colspan="2" align="left"><h2 class="dop_header"><b>{text}</b></h2></td></tr>'


def make_html(rows):
    return f'<html><body><table width="100%" role="presentation"></table><table class="tablebg" width="100%" role="presentation">{"".join(rows)}</table></body></html>'


LISTING = make_html([
    _header("Nov 16, 2026"),
    _row("RBI to conduct 2-day Variable Rate Reverse Repo (VRRR) auction under LAF on November 17, 2026", 70001),
    _row("Auction of Government of India Dated Securities", 70002),
    _row("Money Market Operations as on November 15, 2026", 70003),
    _header("Nov 13, 2026"),
    _row("Government Stock - Full Auction Results", 69990),
    _row("Government Stock - Auction Results: Cut-off", 69989),
    _row("Developments in India&rsquo;s Balance of Payments for the Month of September 2026", 69988),
])


def test_parse_listing_dates_titles_and_urls():
    es = parse_listing(LISTING)
    assert [e.prid for e in es] == ["70001", "70002", "70003", "69990", "69989", "69988"]
    assert es[0].release_date == "2026-11-16" and es[3].release_date == "2026-11-13"
    assert es[5].title == "Developments in India\u2019s Balance of Payments for the Month of September 2026"
    assert es[0].detail_url.endswith("BS_PressReleaseDisplay.aspx?prid=70001")
    assert es[0].pdf_url.endswith(".PDF") and es[0].pdf_url.startswith("https://")


def test_parse_errors_are_explicit():
    with pytest.raises(ParseError):
        parse_listing("<html><body><p>maintenance</p></body></html>")
    with pytest.raises(ParseError):
        parse_listing(make_html([_header("Nov 16, 2026")]))


# ---------------- discovery & store ----------------
def test_discover_new_records_each_release_separately_and_only_once(tmp_path):
    store = PressReleaseStore(tmp_path / "idx.json")
    found = discover_new(parse_listing(LISTING), store)
    assert [(d.item_id, d.entry.prid) for d in found] == [
        ("bop", "69988"), ("cg_result", "69990"), ("vrrr_announcement", "70001"), ("cg_announcement", "70002")]
    assert store.ignored == {"69989", "70003"}
    assert discover_new(parse_listing(LISTING), store) == []        # nothing new -> nothing returned


def test_only_genuinely_new_releases_are_found_next_run(tmp_path):
    store = PressReleaseStore(tmp_path / "idx.json")
    discover_new(parse_listing(LISTING), store)
    newer = make_html([_header("Nov 17, 2026"),
                       _row("Result of the 2-day Variable Rate Reverse Repo (VRRR) auction held on November 17, 2026", 70010)]
                      + [r for r in [LISTING[LISTING.index("<tr>"):LISTING.rindex("</table>")]]])
    found = discover_new(parse_listing(newer), store)
    assert [(d.item_id, d.entry.prid) for d in found] == [("vrrr_result", "70010")]


def test_store_round_trip_and_history(tmp_path):
    p = tmp_path / "idx.json"
    store = PressReleaseStore(p)
    discover_new(parse_listing(LISTING), store)
    store.save()
    again = PressReleaseStore.load(p)
    assert again.records.keys() == store.records.keys() and again.ignored == store.ignored
    assert [r["prid"] for r in again.releases_for("cg_result")] == ["69990"]
    assert json.loads(p.read_text(encoding="utf-8"))["records"]["70002"]["item_id"] == "cg_announcement"


# ---------------- network behaviour (no real network) ----------------
class FakeResp:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text


class FakeSession:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), 0

    def get(self, url, **kw):
        self.calls += 1
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_fetch_retries_transient_errors_then_succeeds():
    s = FakeSession(FakeResp(503), requests.ConnectionError("boom"), FakeResp(200, LISTING))
    assert len(fetch_listing("http://x", s, backoff=0)) == 6 and s.calls == 3


def test_fetch_block_fails_fast_with_status():
    s = FakeSession(FakeResp(403))
    with pytest.raises(FetchError) as e:
        fetch_listing("http://x", s, backoff=0)
    assert e.value.status == 403 and s.calls == 1


def test_fetch_gives_up_after_retries():
    s = FakeSession(FakeResp(500), FakeResp(500), FakeResp(500))
    with pytest.raises(FetchError):
        fetch_listing("http://x", s, backoff=0)
    assert s.calls == 3
