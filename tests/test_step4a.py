import requests

from rbi_tracker import cli
from rbi_tracker.engine import compare
from rbi_tracker.fetch import detail
from rbi_tracker.fetch.listing import FetchError
from engine_data import *  # noqa: F401,F403


# ---------------- VRR / VRRR: under-subscription is never a priority flag ----------------
def test_vrrr_undersubscription_is_not_a_priority_flag():
    ann = rel("vrrr_announcement", "2026-11-12", rows=[{"key": "3D", "notified_amount": 75000}])
    res = rel("vrrr_result", "2026-11-13", rows=[
        {"key": "3D", "notified_amount": 75000, "accepted_amount": 38592, "cutoff_rate": 5.49, "bid_cover": 0.51}])
    d = compare(res, None, announcement=ann)
    assert d.priority_changes == []
    assert not find(d, "undersubscribed")
    c = find(d, "accepted_vs_notified", "3D")[0]          # still reported, just not priority
    assert c.delta == -36408 and not c.priority


def test_vrr_bid_cover_change_still_shown():
    prev = rel("vrr_result", "2026-11-02", rows=[{"key": "4D", "bid_cover": 0.60, "cutoff_rate": 5.50}])
    new = rel("vrr_result", "2026-11-09", rows=[{"key": "4D", "bid_cover": 0.40, "cutoff_rate": 5.50}])
    d = compare(new, prev)
    assert find(d, "bid_cover", "4D")[0].delta == -0.2 and d.priority_changes == []


def test_cg_undersubscription_is_still_priority():
    res = rel("cg_result", "2026-11-14", rows=[{"key": "10Y", "bid_cover": 0.9, "accepted_amount": 100, "notified_amount": 200}])
    d = compare(res, None)
    assert find(d, "undersubscribed", "10Y")[0].priority and find(d, "accepted_vs_notified", "10Y")[0].priority


def test_bop_comparison_is_labelled_prior_period():
    d = compare(BOP_NEW, BOP_PREV)
    assert any("vs prior period" in c.note for c in d.changes)
    assert not any("prior quarter" in c.note for c in d.changes)


# ---------------- detail fetch / capture ----------------
RAW = ('<html><head><title>x</title><script>var a=1;</script><style>p{}</style></head><body>'
       '<form><input type="hidden" name="__VIEWSTATE" value="SECRET"/></form>'
       '<table class="tablebg"><tr><td style="color:red" onclick="go()">Government Stock Full Auction Results'
       '</td></tr><tr><td>Notified Amount</td><td>34,000</td></tr></table></body></html>')


def test_clean_html_keeps_content_drops_noise():
    out = detail.clean_html(RAW)
    assert "Notified Amount" in out and "34,000" in out
    assert "SECRET" not in out and "var a=1" not in out and "onclick" not in out and "style=" not in out


class _Resp:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text


class _Sess:
    def __init__(self, *rs):
        self.rs = list(rs)

    def get(self, url, **kw):
        r = self.rs.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_fetch_detail_retries_then_succeeds_and_blocks_fail_fast():
    assert detail.fetch_detail_html("1", _Sess(_Resp(500), requests.ConnectionError("x"), _Resp(200, RAW)),
                                    backoff=0) == RAW
    try:
        detail.fetch_detail_html("1", _Sess(_Resp(403)), backoff=0)
    except FetchError as e:
        assert e.status == 403
    else:
        raise AssertionError("expected FetchError")


def test_capture_saves_files_and_one_failure_does_not_block_the_rest(tmp_path, monkeypatch):
    def fake_fetch(prid):
        if prid == "2":
            raise FetchError("HTTP 500", status=500)
        return RAW
    monkeypatch.setattr(cli, "fetch_detail_html", fake_fetch)
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)
    rc = cli.main(["capture", "1", "2", "3", "--out", str(tmp_path)])
    assert rc == 1                                           # reports the failure ...
    assert (tmp_path / "1.html").exists() and (tmp_path / "3.html").exists()   # ... but 1 and 3 were saved
    assert not (tmp_path / "2.html").exists()
