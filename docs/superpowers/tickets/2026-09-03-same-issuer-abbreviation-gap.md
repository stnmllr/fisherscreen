# Ticket: `_same_issuer` drops an ADR line whose name abbreviates the issuer (`ENDEAVOUR MNG` vs `ENDEAVOUR MINING`)

**Opened:** 2026-09-03
**Priority:** non-blocking today, but it gets *quieter* with the quant-only dossier. No wrong number is produced — a real US ADR line can be silently dropped, and after the quant-only change that no longer aborts loudly but yields a plausible-looking degraded dossier. See "Why the urgency changed" below.
**Status:** open — voraussichtlich gegenstandslos, siehe Update

## Update 2026-09-04: der Ankerpfad entfernt den Vergleich, statt ihn zu reparieren

`_classify_us_line` sucht US-Linien nicht mehr per Volltextsuche über den Emittentennamen,
sondern über die `shareClassFIGI` der Heimatlinie (Ticket
`tickets/2026-09-04-openfigi-search-unpaginated.md`). Die Aktiengattung **ist** die
Identität, also gibt es auf diesem Pfad keinen Namensabgleich mehr — und damit auch die
hier beschriebene Abkürzungslücke nicht.

Belege aus dem Zähllauf, bevor die Änderung landete: von 15 `no_us_line`-Titeln waren
genau **2** echte Kandidaten (`MONY.L`, `VCT.PA`) — US-Linien vorhanden, von
`_same_issuer` sämtlich verworfen. Beide sollten über den Anker von selbst aufgehen.

`_same_issuer` bleibt vorerst bestehen, weil der befristete `search_issuer`-Rückfall für
Heimatlinien ohne `shareClassFIGI` ihn noch benutzt. Fällt dieser Rückfall (er wird
gelöscht, sobald ein Zähllauf zeigt, dass seine WARNING nie feuert), fällt dieses Ticket
mit ihm.

**Vor dem Schließen zu prüfen:** ein Zähllauf nach der Änderung muss zeigen, dass
`MONY.L` und `VCT.PA` nicht mehr im Topf `no_us_line` landen. Erst dann ist die Lücke
belegt geschlossen statt vermutet.

## Context

While diagnosing why `deepdive EDV.L` failed (Endeavour Mining plc — the answer turned
out to be that the issuer is not an SEC registrant at all), the OpenFIGI trace showed
**two** US lines for the issuer:

```
US EDVMF      PQ   type='Common Stock'       name='ENDEAVOUR MINING PLC'
US ENVMY      PQ   type='Depositary Receipt' name='ENDEAVOUR MNG PLC-UNSPON ADR'
```

`pick_us_adr_line` (`app/deepdive/eu_adr_resolution.py:127-153`) is documented to
**prefer the Depositary-Receipt line**. It picked `EDVMF` — the plain OTC common-stock
line — instead. The DR line never reached the preference loop, because
`_same_issuer` (`:117-124`) filtered it out of the `us` list first:

```
ident_norm                                    -> ENDEAVOURMINING
'ENDEAVOUR MINING PLC'        -> norm        -> ENDEAVOURMINING          _same_issuer True
'ENDEAVOUR MNG PLC-UNSPON ADR'-> norm        -> ENDEAVOURMNG-UNSPONADR   _same_issuer False
```

### Root cause: two independent defects that happen to coincide here

1. **The abbreviation is mid-string.** `_same_issuer` is deliberately prefix-tolerant —
   its docstring names `'ASML HOLDING NV-NY REG SHS'` and `'SAP SE-SPONSORED ADR'` as
   the cases it exists for, and prefix tolerance handles those correctly because the
   *head* of the name is intact and only a descriptor is appended. Here the ADR line
   abbreviates the issuer itself: `MNG` instead of `MINING`. `ENDEAVOURMNG…` is not a
   prefix of `ENDEAVOURMINING` and vice versa, so no amount of prefix tolerance helps.
2. **The descriptor survives `issuer_name`.** `issuer_name` (`:74-84`) strips a trailing
   `-CLASSTOKEN` only when the token contains no space — the guard that keeps
   `COCA-COLA CO` intact. `-UNSPON ADR` contains a space, so it is not stripped and
   ends up inside the normalised string as `-UNSPONADR`. On its own this is survivable
   (prefix tolerance absorbs a trailing descriptor); combined with defect 1 it is not.

Note that defect 2 alone would also bite `'SAP SE-SPONSORED ADR'` if the head were not
intact — the existing docstring example works only because `norm_issuer` happens to
reduce `SAP SE` to `SAP`, which *is* a prefix of `SAP-SPONSOREDADR`.

### Why this was harmless for EDV.L specifically

`ENVMY` is an **unsponsored** ADR and is likewise absent from
`company_tickers.json` — `edgar.get_cik("ENVMY")` returns `None`, exactly like
`EDVMF`. Preferring the DR line would have changed which symbol appears in the error
path, not the outcome. EDV.L has no SEC source either way.

So this ticket is **not** about EDV.L. EDV.L is only how the defect became visible.

## Why the urgency changed with the quant-only dossier

Before the quant-only change, the damage case was loud: an issuer whose **only** US
line is an abbreviated DR line would make `pick_us_adr_line` return `None`, the
resolver would raise `DeepDiveError("no US ADR line … pure-EU listing")`, the CLI would
exit 1, and a human would notice a claim that contradicts reality.

After the quant-only change that same path returns a `no_us_line` verdict and writes a
**quant-only dossier**, exit 0. The dossier honestly says "no US listing, therefore no
SEC source" — but for this class of issuer that statement is **false**: there is a US
ADR line, there is a CIK behind it, and there may well be a 20-F that Tool B could have
read. The failure mode moves from "loud and wrong" to "quiet and wrong", which is the
worse of the two. The quant-only change is still right; this ticket is the compensating
guard.

## Not a duplicate of the ISIN anchor ticket

`tickets/2026-06-03-isin-canonical-anchor-openfigi.md` proposes replacing name matching
with an ISIN-based canonical anchor, which would dissolve this problem rather than fix
it. That is the better long-term answer and this ticket should be **closed in favour of
it** if the ISIN anchor is implemented first. Until then the name path is what runs in
production, and it has a known hole. Scope here is deliberately the cheap guard, not
the redesign.

Related but distinct: `tickets/2026-08-20-toolA-toolB-symbol-join-key.md` concerns the
Tool-A/Tool-B join key, i.e. issuer identity *across our own two tools*, not issuer
identity *within one OpenFIGI response*.

## Scope (this ticket)

- **Quantify before fixing.** The EU-exposure sweep (the four-bucket measurement over
  the 416 dotted tickers in `data/universe.json`) already has to call
  `search_issuer` for every EU title. Count, as a by-product, how many issuers have a
  US line that `_same_issuer` rejects while a *different* US line of the same issuer is
  accepted — and how many are rejected with **no** accepted sibling. Only the second
  group is a real false negative. If that group is empty across 416 titles, downgrade
  this ticket to a comment rather than building a matcher.
- **Decide the matcher, if the count justifies one.** Options, cheapest first:
  token-subset matching after dropping listing descriptors (`ADR`, `SPONSORED`,
  `UNSPON`, `REG`, `SHS`, `NY`); an abbreviation-tolerant comparison (initial-prefix per
  token, so `MNG` matches `MINING`); or anchoring on `shareClassFIGI` / `compositeFIGI`
  instead of the name — the FIGI fields are already present in every line of the
  response and are identity-bearing in a way the display name is not.
- **Extend `issuer_name`'s descriptor stripping** to trailing tokens that contain a
  space, guarded so real hyphenated names survive. The existing no-space guard is
  documented as protecting `COCA-COLA CO`; a descriptor allow-list would protect it just
  as well and would strip `-UNSPON ADR`.
- **Regression fence.** Whatever is chosen must keep the two documented cases working
  (`ASML HOLDING NV-NY REG SHS`, `SAP SE-SPONSORED ADR`) and must not re-admit the false
  hit that prefix tolerance was introduced to prevent (`ROCHE` vs `ROCHE BOBOIS`, see
  `find_home_identity`'s NAME-SANITY-CHECK at `:100-114`).

## Out of scope

- The ISIN canonical anchor itself — that is
  `tickets/2026-06-03-isin-canonical-anchor-openfigi.md`. This ticket should either be
  consumed by that decision or explicitly choose the cheap matcher and say why.
- Getting the *canonical* NYSE ADR symbol rather than an OTC foreign-ordinary. That is
  the paginated-search problem already documented as deferred (YAGNI) in
  `pick_us_adr_line`'s docstring; it yields no CIK gain and is unrelated to this
  matching defect.
- Unsponsored ADRs as a class. `ENVMY` is unsponsored and would not have produced a
  filing source anyway; the question of whether an unsponsored line should even be
  considered is a separate policy question.

## Reproduction

`uv run python scripts\diagnose_eu_adr_trace.py EDV.L` prints the full OpenFIGI line
list (US lines marked) and the line `pick_us_adr_line` actually chose.
`uv run python scripts\diagnose\diagnose_edv_envmy.py` reduces the case to the
four-line norm comparison quoted above, including the `_same_issuer` verdict per name.
