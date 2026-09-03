from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Literal, get_args

from app.errors import DeepDiveError

if TYPE_CHECKING:
    from app.services.edgar_client import EdgarClient

# Heuristic from negative-filters-status.md §3.1 / Master ADR-1: a "." in the
# ticker marks a non-US listing (e.g. NOVO-B.CO, SAP.DE). US tickers have none.
#
# PRECONDITION: tickers are yfinance/Yahoo-suffix style (the convention used by
# data/universe.json) — US class shares are "BRK-B", NOT "BRK.B". Under that
# convention a "." reliably marks a non-US exchange suffix. Feeding a dotted US
# class-share ticker (BRK.B) would raise DeepDiveError; that is acceptable and
# matches the ADR-1 heuristic. The marker routes dotted EU tickers to the dynamic
# OpenFIGI EU-ADR resolver (delegate `eu_resolver`, wired in PR #43); it is a
# routing signal, not a fallback awaiting removal.
_EU_MARKER = "."

# Structural reasons why a ticker has no SEC filing source at all. These are
# statements about the issuer's registration status, not about a failed call —
# a transient API error is a DataSourceError and must never land here.
NoSecSourceReason = Literal["no_us_line", "not_sec_registrant", "no_annual_form"]
# Derived from the type, never hand-listed: the cache validator in
# eu_adr_resolution must not be able to drift from the literal.
NO_SEC_SOURCE_REASONS: frozenset[str] = frozenset(get_args(NoSecSourceReason))


@dataclass(frozen=True)
class ResolvedTicker:
    """Outcome of ticker resolution: either a usable filing source (cik +
    form_type) or a structural no-SEC-source verdict (reason + note). The
    __post_init__ biconditional makes the half-resolved middle unconstructible."""

    ticker: str
    adr_ticker: str | None
    cik: str | None
    form_type: str | None
    no_sec_source_reason: NoSecSourceReason | None = None
    no_sec_source_note: str | None = None

    def __post_init__(self) -> None:
        # A: a verdict exists exactly when the filing source does not.
        assert (self.no_sec_source_reason is None) == (
            self.cik is not None and self.form_type is not None
        ), "ResolvedTicker: no_sec_source_reason excludes cik+form_type, and vice versa"
        # B: A alone still admits cik set / form_type None with a reason —
        # a no-source verdict must carry no filing handles and must explain itself.
        assert self.no_sec_source_reason is None or (
            self.cik is None
            and self.form_type is None
            and self.no_sec_source_note is not None
        ), "ResolvedTicker: a no-SEC-source verdict needs a note and no cik/form_type"

    @property
    def has_filing_source(self) -> bool:
        return self.no_sec_source_reason is None


def no_sec_source(
    ticker: str, *, reason: NoSecSourceReason, note: str
) -> ResolvedTicker:
    """Single factory for the degraded verdict, so no call site invents a shape.

    Discovered symbols or CIKs belong into the note prose only — putting them
    into adr_ticker/cik would suggest a filing path that does not exist."""
    return ResolvedTicker(
        ticker=ticker,
        adr_ticker=None,
        cik=None,
        form_type=None,
        no_sec_source_reason=reason,
        no_sec_source_note=note,
    )


class ADRResolver:
    """Resolver: static ADR table (override, Master ADR-1) -> US-path CIK
    resolution via the EDGAR client -> dynamic EU-ADR resolution (OpenFIGI,
    delegated to `eu_resolver`, wired in PR #43) for dotted EU tickers.

    The EU delegate returns a degraded ResolvedTicker (no_sec_source_reason set)
    when the issuer structurally has no SEC filing source. The US path splits the
    two cases instead of treating them alike: a missing CIK stays fatal
    (DeepDiveError — the symbol itself is unverified, so it may simply be a typo),
    a missing annual form degrades to the same quant-only verdict as the EU path
    (identity already proven via the SEC ticker map) — see the comments there."""

    def __init__(
        self,
        table: dict[str, dict[str, str]],
        edgar: "EdgarClient",
        eu_resolver: Callable[[str], ResolvedTicker],
    ) -> None:
        self._table = {k.upper(): v for k, v in table.items()}
        self._edgar = edgar
        self._eu_resolver = eu_resolver

    def resolve(self, ticker: str) -> ResolvedTicker:
        key = ticker.upper()
        entry = self._table.get(key)
        if entry is not None:
            return ResolvedTicker(
                ticker=ticker,
                adr_ticker=entry["adr_ticker"],
                cik=entry["cik"],
                form_type=entry["form_type"],
            )
        if _EU_MARKER in ticker:
            # Dynamic EU-ADR resolution (OpenFIGI). The delegate returns a degraded
            # ResolvedTicker for a structural no-SEC-source issuer (no US line, no
            # CIK, no annual form -> quant-only dossier), raises DeepDiveError for an
            # unverifiable identity and DataSourceError on a transient API failure —
            # failure != empty, never a silent wrong match.
            return self._eu_resolver(ticker)
        # US path: resolve the CIK + detect the annual form from EDGAR.
        cik = self._edgar.get_cik(ticker)
        # ASYMMETRY, DELIBERATE — and now the ONLY one left between the paths: the
        # EU path degrades a missing CIK to a quant-only dossier, the US path aborts.
        # For a dotted EU ticker the home identity has been verified via OpenFIGI
        # first, so "no CIK" provably means "not an SEC registrant". For an undotted
        # US symbol nothing verifies the input, so "no CIK" is indistinguishable from
        # a typo — degrading would silently produce a plausible-looking dossier for a
        # ticker that does not exist. Do not "harmonise" this with the degrading
        # branch below: there the CIK already proves the issuer exists, here nothing
        # does. The two branches answer different questions.
        if not cik:
            raise DeepDiveError(
                f"US ticker {ticker} not found in the SEC company_tickers map — "
                f"check the symbol or add an ADR table entry."
            )
        form = self._edgar.detect_annual_form(cik)
        # Degraded, exactly like the EU path: past the CIK lookup the identity is
        # proven (the CIK comes from the SEC ticker map), so a missing annual form
        # is a statement about the issuer, not about the input. A registrant that
        # files only 40-F, 10-Q or F-6 is a structural gap — the Phase-2 "other
        # forms" gap — not a typo, and the same finding must not mean exit 1 for a
        # US symbol and exit 0 for a dotted EU ticker.
        if form is None:
            return no_sec_source(
                ticker,
                reason="no_annual_form",
                note=(
                    f"Kein SEC-Hard-Scuttlebutt: {ticker} (CIK {cik}) reicht weder "
                    f"10-K noch 20-F ein — andere Jahresformulare (40-F, F-6) sind "
                    f"Phase 2. Dossier ist quant-only (Quant + Bewertung + Peers)."
                ),
            )
        return ResolvedTicker(
            ticker=ticker, adr_ticker=None, cik=cik.zfill(10), form_type=form
        )
