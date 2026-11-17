"""extract(item_id, html, ...) -> Release : the single entry point from a release page to engine input."""
from __future__ import annotations

from datetime import date

from ..engine.models import Release
from . import auctions as A
from . import publications as P
from .common import ExtractionError, load, release_meta

EXTRACTORS = {
    "cg_announcement": A.cg_announcement,
    "cg_result": A.cg_result,
    "sg_announcement": A.sg_announcement,
    "sg_result": A.sg_result,
    "tbill_announcement": A.tbill_announcement,
    "tbill_result": A.tbill_result,
    "omo_result": A.omo_result,
    "vrr_announcement": A.vrr_announcement,
    "vrr_result": A.vrr_result,
    "vrrr_announcement": A.vrr_announcement,
    "vrrr_result": A.vrr_result,
    "bop": P.bop,
    "wss": P.wss,
    "mpc_minutes": P.mpc_minutes,
    "sectoral_credit": P.sectoral_credit_text,
}


def extract(item_id: str, html: str, *, release_date: str | None = None, source_url: str = "",
            maturities: dict[str, str] | None = None) -> Release:
    """Turn one release page into a `Release` (the engine's input contract).

    release_date: use the date from the press release listing when known; else read from the page.
    maturities: {security name: ISO maturity date} from earlier announcements (CG result tenor buckets).
    """
    fn = EXTRACTORS.get(item_id)
    if fn is None:
        raise ExtractionError(f"no extractor yet for {item_id!r}")
    soup = load(html)
    page_date, reference = release_meta(soup)
    rdate = release_date or page_date
    if not rdate:
        raise ExtractionError("release date not found on the page and none supplied")
    date.fromisoformat(rdate)
    fields, rows = fn(soup, {"release_date": rdate, "maturities": maturities or {}})
    prior_year = fields.pop("_prior_year", {})
    return Release(item_id=item_id, release_date=rdate, reference=reference, source_url=source_url,
                   fields=fields, rows=rows, prior_year=prior_year)