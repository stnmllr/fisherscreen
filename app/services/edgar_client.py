import logging
import random
import re
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable, Protocol

import httpx

from app.errors import DataSourceError
from app.services.rate_limiter import (
    DEFAULT_EDGAR_MAX_REQUESTS_PER_SECOND,
    RateLimiter,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RawFiling:
    accession_number: str
    document_text: str
    filing_date: str | None = None


@dataclass(frozen=True)
class Form4Ref:
    accession_number: str
    primary_document: str
    filing_date: str


@dataclass(frozen=True)
class GoingConcernHit:
    accession_number: str | None
    file_type: str | None
    file_date: str | None


class EdgarClient(Protocol):
    def get_cik(self, ticker: str) -> str | None: ...
    def has_restatement(self, cik: str, years: int = 3) -> bool: ...
    def has_going_concern(self, cik: str, months: int = 24) -> bool: ...
    def going_concern_hit(self, cik: str, months: int = 24) -> "GoingConcernHit | None": ...
    def has_active_enforcement(self, cik: str) -> bool: ...
    def get_latest_annual_filing(self, cik: str, form_type: str) -> RawFiling: ...
    def detect_annual_form(self, cik: str) -> str | None: ...
    def get_form4_index(self, cik: str, since: str) -> list["Form4Ref"]: ...
    def get_form4_document(
        self, cik: str, accession_number: str, primary_document: str
    ) -> str: ...


class EdgarClientImpl:
    _SEC_BASE = "https://data.sec.gov"
    _EFTS_BASE = "https://efts.sec.gov"
    _EFTS_MAX_ATTEMPTS = 5
    _EFTS_BACKOFF_BASE_SECONDS = 1.0  # full-jitter cap for retry N is base * 2**(N-1)
    _EFTS_OVERBROAD_CAP = 10000  # EFTS caps hits.total.value here when unscoped/over-broad
    _GC_PRIMARY_FORMS = ("10-K", "10-Q")  # count the phrase only in the primary filing doc

    # --- SUB-PHASE 4: going-concern polarity discriminator ---
    # Every 10-K/10-Q carries the ASC-205-40 "substantial doubt" phrase as boilerplate
    # (the evaluation duty). A phrase occurrence is an AFFIRMATIVE going-concern finding
    # ONLY IF, within its GOVERNING CLAUSE (the phrase back to the previous sentence
    # terminator, bounded by ~400 chars), there is NO "whether" duty, NO negation, and
    # NO hypothetical modal. We OR the affirmative verdicts across ALL occurrences:
    # going_concern is True iff ≥1 occurrence is affirmative (a doc may contain both the
    # duty-intro and a real finding, e.g. FRQN).
    # We anchor on the bare phrase "substantial doubt" and judge polarity from its
    # GOVERNING CLAUSE. This subsumes every affirmative form generously — "[these]
    # factors raise substantial doubt", "there is substantial doubt", "substantial
    # doubt exists" are all just the phrase sitting in a clause with no rejection token.
    _GC_PHRASE_RE = re.compile(r"substantial\s+doubt", re.IGNORECASE)
    # Clause-scoping: a generous backward window when no sentence terminator is found.
    _GC_CLAUSE_MAX_CHARS = 400
    _GC_CLAUSE_TERMINATORS = ".;:"
    # Rejection tokens scanned across the WHOLE governing clause before the phrase.
    _GC_WHETHER_RE = re.compile(r"\bwhether\b", re.IGNORECASE)
    _GC_MODAL_RE = re.compile(r"\b(?:may|might|could|would)\b", re.IGNORECASE)
    _GC_NEGATION_RE = re.compile(
        r"\b(?:no|not|never|free\s+from|without|absence\s+of)\b", re.IGNORECASE
    )

    def __init__(
        self,
        user_agent: str,
        *,
        max_requests_per_second: float = DEFAULT_EDGAR_MAX_REQUESTS_PER_SECOND,
        rate_limiter: RateLimiter | None = None,
        efts_sleep: Callable[[float], None] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        if not user_agent:
            raise DataSourceError(
                "EDGAR user agent not set — configure FISHERSCREEN_EDGAR_USER_AGENT"
            )
        self._headers = {"User-Agent": user_agent}
        self._ticker_map: dict[str, str] | None = None
        self._rate_limiter = (
            rate_limiter
            if rate_limiter is not None
            else RateLimiter(max_requests_per_second)
        )
        # EFTS backoff is injected separately from the rate-limiter clock so tests
        # can capture delays + pin the jitter deterministically without real sleeps
        # or real randomness. Default to time.sleep / a fresh Random() in production.
        self._efts_sleep: Callable[[float], None] = (
            efts_sleep if efts_sleep is not None else time.sleep
        )
        self._rng: random.Random = rng if rng is not None else random.Random()

    def _get(self, url: str) -> dict[str, Any]:
        self._rate_limiter.acquire()
        try:
            resp = httpx.get(url, headers=self._headers, timeout=30)
        except Exception as exc:
            raise DataSourceError(f"EDGAR HTTP request failed: {exc}") from exc
        if resp.status_code != 200:
            raise DataSourceError(f"EDGAR returned {resp.status_code} for {url}")
        return resp.json()

    def _load_ticker_map(self) -> dict[str, str]:
        """Fetch SEC company_tickers.json and return a TICKER -> CIK string map."""
        url = "https://www.sec.gov/files/company_tickers.json"
        data = self._get(url)
        return {entry["ticker"].upper(): str(entry["cik_str"]) for entry in data.values()}

    def get_cik(self, ticker: str) -> str | None:
        """Return the SEC CIK for ticker, or None if not found or on fetch failure.

        The ticker map is loaded lazily on first call and cached for the lifetime
        of this client instance to avoid repeated HTTP requests.
        """
        if self._ticker_map is None:
            try:
                self._ticker_map = self._load_ticker_map()
            except DataSourceError as exc:
                logger.warning("edgar: failed to load ticker map: %s — CIK lookup disabled", exc)
                self._ticker_map = {}  # empty dict prevents repeated retries
        return self._ticker_map.get(ticker.upper())

    def has_restatement(self, cik: str, years: int = 3) -> bool:
        padded = cik.zfill(10)
        url = f"{self._SEC_BASE}/submissions/CIK{padded}.json"
        data = self._get(url)
        cutoff = (date.today() - timedelta(days=years * 365)).isoformat()
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        items_list = recent.get("items", [])
        for form, filing_date, items in zip(forms, dates, items_list):
            if form == "8-K" and filing_date >= cutoff and "4.02" in str(items):
                return True
        return False

    def _get_efts(self, url: str) -> dict[str, Any]:
        """GET an EFTS search URL with bounded retry on transient 5xx.

        EFTS (efts.sec.gov) sporadically returns HTTP 500 on /search-index — server
        flakiness, NOT rate-limiting (a rate-exceed is 403, never observed). A
        transient 5xx must not randomly flip a ticker between "kept" and "dropped",
        so retry up to ``_EFTS_MAX_ATTEMPTS`` times with EXPONENTIAL FULL-JITTER
        backoff: the sleep before retry N is ``uniform(0, base * 2**(N-1))`` with
        ``base = _EFTS_BACKOFF_BASE_SECONDS``. Full jitter (uniform 0..cap, not a
        fixed value) decouples synchronised retries under full-universe load. Each
        retry logs a WARNING so a genuine persistent EFTS outage surfaces loudly
        instead of being silently masked by the retry.
        """
        for attempt in range(1, self._EFTS_MAX_ATTEMPTS + 1):
            self._rate_limiter.acquire()
            try:
                resp = httpx.get(url, headers=self._headers, timeout=30)
            except Exception as exc:
                raise DataSourceError(f"EDGAR HTTP request failed: {exc}") from exc
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code < 500 or attempt == self._EFTS_MAX_ATTEMPTS:
                raise DataSourceError(f"EDGAR returned {resp.status_code} for {url}")
            logger.warning(
                "edgar: EFTS returned %s for %s — transient, retry %d/%d",
                resp.status_code, url, attempt, self._EFTS_MAX_ATTEMPTS,
            )
            cap = self._EFTS_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            self._efts_sleep(self._rng.uniform(0, cap))
        # unreachable: loop either returns 200 or raises on the final attempt
        raise DataSourceError(f"EDGAR EFTS retry loop exited without result for {url}")

    def has_going_concern(self, cik: str, months: int = 24) -> bool:
        return self.going_concern_hit(cik, months) is not None

    @staticmethod
    def _strip_html(html: str) -> str:
        """Fast tag strip + whitespace collapse — NO BeautifulSoup.

        A cold run fetches one large primary doc for nearly every US ticker (all carry
        the boilerplate), so a full DOM parse per doc is prohibitive. A regex strip is
        enough to land the phrase + its governing clause on a single flat string.
        """
        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", text).strip()

    def _governing_clause(self, text: str, phrase_start: int) -> str:
        """The clause governing a phrase occurrence: from the phrase back to the
        previous sentence terminator (.;:), bounded by ~400 chars if none is found.

        Clause-scoped, NOT a token window: WTW/HIMS put the negation ~10+ words before
        'raise', so a check on the immediately-preceding token misses it and reproduces
        the false positive. We scan the entire governing clause for the rejection tokens.
        """
        window_start = max(0, phrase_start - self._GC_CLAUSE_MAX_CHARS)
        clause_start = window_start
        for idx in range(phrase_start - 1, window_start - 1, -1):
            if text[idx] in self._GC_CLAUSE_TERMINATORS:
                clause_start = idx + 1
                break
        return text[clause_start:phrase_start]

    def _has_affirmative_going_concern(self, text: str) -> bool:
        """True iff ≥1 'substantial doubt' occurrence is an affirmative going-concern
        finding — i.e. its governing clause carries NO 'whether' duty, NO negation, and
        NO hypothetical modal. Iterates EVERY occurrence and ORs the verdicts.

        Direction: True DROPS the ticker. Affirmative patterns are generous; the
        rejection is clause-scoped and reliable so boilerplate (the FP bug) is not
        over-accepted while a real distressed finding (FRQN) is not over-rejected.
        """
        flat = self._strip_html(text)
        # ∃-affirmative over ALL "substantial doubt" occurrences: an occurrence is
        # affirmative iff its GOVERNING CLAUSE carries no whether-duty, no negation and
        # no hypothetical modal. A doc may hold both the duty-intro and a real finding
        # (FRQN), so we iterate every occurrence and short-circuit on the first clean one.
        for match in self._GC_PHRASE_RE.finditer(flat):
            clause = self._governing_clause(flat, match.start())
            if self._GC_WHETHER_RE.search(clause):
                continue
            if self._GC_NEGATION_RE.search(clause):
                continue
            if self._GC_MODAL_RE.search(clause):
                continue
            return True
        return False

    def going_concern_hit(self, cik: str, months: int = 24) -> "GoingConcernHit | None":
        padded = cik.zfill(10)
        startdt = (date.today() - timedelta(days=months * 30)).isoformat()  # ~30 days/month approximation
        base_url = (
            f"{self._EFTS_BASE}/LATEST/search-index"
            f"?q=%22raise+substantial+doubt%22"
            f"&forms=10-K,10-Q"
            f"&dateRange=custom&startdt={startdt}"
            f"&ciks={padded}"  # valid EFTS scoping param; `entity=` is silently ignored
        )
        # EFTS scopes `ciks=` and `forms=`, but SILENTLY IGNORES `startdt` (byte-proven:
        # the CIK-scoped query returns the same hit set with and without startdt). So the
        # date window MUST be enforced CLIENT-SIDE, per hit, on `_source.file_date`. And
        # `forms=10-K,10-Q` only scopes the SUBMISSION; the matching document inside it can
        # be an EX-* exhibit carrying auditor-responsibility boilerplate ("required to
        # evaluate whether there are conditions … that raise substantial doubt …"), which
        # is NOT a going-concern qualification (observed at AWI). So count the phrase only
        # in PRIMARY form documents (`_source.file_type` in {10-K, 10-Q}). That window +
        # form check is a CHEAP PRE-FILTER only: every healthy 10-K/10-Q ALSO carries the
        # ASC-205-40 phrase as boilerplate (evaluation duty / negation / hypothetical),
        # so a surviving candidate must additionally have its PRIMARY DOCUMENT fetched
        # and pass the polarity discriminator (`_has_affirmative_going_concern`).
        # going_concern is True iff some candidate's doc has ≥1 affirmative occurrence.
        frm = 0
        while True:
            data = self._get_efts(f"{base_url}&from={frm}")
            total = data.get("hits", {}).get("total", {})
            value = total.get("value", 0)
            relation = total.get("relation", "eq")
            # Over-broad sentinel: a CIK-scoped query returns relation == "eq" with a
            # tiny exact count. relation == "gte" (or a value pinned at the cap) means
            # the result set was capped/approximate → the query was NOT effectively
            # scoped. Treating that as going_concern=True would drop every US ticker,
            # so fail LOUD instead: DataSourceError → runner skips+keeps (E5) and logs.
            if relation == "gte" or value >= self._EFTS_OVERBROAD_CAP:
                raise DataSourceError(
                    f"EFTS returned an over-broad/capped result for cik={cik} "
                    f"(value={value}, relation={relation}) — query scoping likely broken; "
                    f"refusing to treat as a going-concern signal"
                )
            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                return None
            for hit in hits:
                source = hit.get("_source", {})
                file_date = source.get("file_date") or ""
                file_type = source.get("file_type") or ""
                if not (file_date >= startdt and file_type in self._GC_PRIMARY_FORMS):
                    continue
                # Pre-filter passed → fetch the primary doc and discriminate on polarity.
                # A fetch failure raises DataSourceError (fail-safe: runner keeps the
                # ticker, no silent drop). Boilerplate → not affirmative → keep scanning.
                doc_url = self._gc_doc_url(cik, hit)
                if doc_url is None:
                    continue
                document = self._get_text(doc_url)
                if self._has_affirmative_going_concern(document):
                    return GoingConcernHit(
                        accession_number=source.get("adsh"),
                        file_type=file_type,
                        file_date=file_date,
                    )
            frm += len(hits)
            if frm >= value:
                return None

    def _gc_doc_url(self, cik: str, hit: dict[str, Any]) -> str | None:
        """Build the primary-document archive URL from an EFTS hit.

        The hit ``_id`` is ``"{accession}:{filename}"``. The archive URL is
        ``https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_nodash}/{filename}``.
        Returns None if the ``_id`` lacks the ``accession:filename`` shape (no doc to fetch).
        """
        hit_id = hit.get("_id") or ""
        accession, sep, filename = hit_id.partition(":")
        if not sep or not filename:
            return None
        acc_nodash = accession.replace("-", "")
        return (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{int(cik)}/{acc_nodash}/{filename}"
        )

    def has_active_enforcement(self, cik: str) -> bool:
        """Deliberately inert no-op.

        Enforcement screening (Fisher Point 15 / integrity) is not implemented
        yet, so this always returns ``False`` (no enforcement signal). It
        intentionally does NOT log per CIK — doing so produced 538 WARNING lines
        of pure noise in a full run. The method and its call seam in
        ``app/screener/runner.py::_evaluate_edgar`` are kept so the Protocol
        contract stays stable for the future implementation.
        See ``docs/superpowers/tickets/2026-06-03-enforcement-screening.md``.
        """
        return False

    def _get_text(self, url: str) -> str:
        self._rate_limiter.acquire()
        try:
            resp = httpx.get(url, headers=self._headers, timeout=60)
        except Exception as exc:
            raise DataSourceError(f"EDGAR HTTP request failed: {exc}") from exc
        if resp.status_code != 200:
            raise DataSourceError(f"EDGAR returned {resp.status_code} for {url}")
        return resp.text

    def get_latest_annual_filing(self, cik: str, form_type: str) -> RawFiling:
        padded = cik.zfill(10)
        data = self._get(f"{self._SEC_BASE}/submissions/CIK{padded}.json")
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        dates = recent.get("filingDate", [])
        for idx, (form, accession, primary) in enumerate(
            zip(forms, accessions, primary_docs)
        ):
            if form == form_type:
                filing_date = dates[idx] if idx < len(dates) else None
                cik_int = str(int(cik))
                acc_nodash = accession.replace("-", "")
                url = (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{cik_int}/{acc_nodash}/{primary}"
                )
                text = self._get_text(url)
                return RawFiling(
                    accession_number=accession,
                    document_text=text,
                    filing_date=filing_date,
                )
        raise DataSourceError(
            f"no {form_type} filing found for CIK {padded} in recent submissions"
        )

    def detect_annual_form(self, cik: str) -> str | None:
        """Most recent annual form the filer uses: '10-K' (US domestic) or
        '20-F' (foreign private issuer). None if neither appears in recent
        submissions. A network failure raises DataSourceError via self._get
        (failure != empty, ADR-BF-5) — None means 'genuinely no annual form'."""
        padded = cik.zfill(10)
        data = self._get(f"{self._SEC_BASE}/submissions/CIK{padded}.json")
        forms = data.get("filings", {}).get("recent", {}).get("form", [])
        for form in forms:
            if form in ("10-K", "20-F"):
                return form
        return None

    def get_form4_index(self, cik: str, since: str) -> list[Form4Ref]:
        """Form-4 refs filed on/after `since` (ISO date). Deliberate single
        re-fetch of submissions.json (negligible vs the N per-XML pulls)."""
        padded = cik.zfill(10)
        data = self._get(f"{self._SEC_BASE}/submissions/CIK{padded}.json")
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accs = recent.get("accessionNumber", [])
        docs = recent.get("primaryDocument", [])
        dates = recent.get("filingDate", [])
        refs: list[Form4Ref] = []
        oldest: str | None = None
        for i, form in enumerate(forms):
            d = dates[i] if i < len(dates) else None
            if d and (oldest is None or d < oldest):
                oldest = d
            if form == "4" and d and d >= since:
                refs.append(Form4Ref(accs[i], docs[i], d))
        if oldest is not None and oldest > since:
            logger.warning(
                "edgar: form-4 window starts %s but oldest recent filing is %s "
                "(cik=%s) — older Form-4 not in recent (files-overflow not implemented)",
                since, oldest, cik,
            )
        return refs

    def get_form4_document(
        self, cik: str, accession_number: str, primary_document: str
    ) -> str:
        """Raw Form-4 XML. primaryDocument is the xslF.../ HTML render path;
        strip the prefix to reach the raw .xml in the same accession folder."""
        cik_int = str(int(cik))
        acc_nodash = accession_number.replace("-", "")
        raw_doc = primary_document.split("/")[-1]
        url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{cik_int}/{acc_nodash}/{raw_doc}"
        )
        return self._get_text(url)
