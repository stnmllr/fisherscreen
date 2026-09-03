# Ticket: Tool B mixes currencies without saying so — peer table has no currency at all, and debt/cash are labelled with the wrong one

**Opened:** 2026-09-03
**Priority:** correctness, but quieter than the minor-unit defect it was found beside. Wrong *comparisons*, not wrong arithmetic within one figure. Affects any dossier whose peer set or reporting currency differs from the listing currency — i.e. most European ones.
**Status:** open

## Context

Found while fixing the GBp minor-unit mislabel
(`tickets/2026-09-03-toolB-minor-unit-gbp-mislabel.md`). That one was a **unit** problem
inside a single currency — pence vs. pounds. These two are a different class: **currency**
problems. They were deliberately left out of that change so the two classes would not get
entangled, since the fix for one does nothing for the other.

### (a) The peer table carries no currency whatsoever

`PeerQuant` (`app/models/deep_dive_record.py:120-121`) holds `free_cashflow` and
`market_cap` with no currency field, and `app/deepdive/peer_quant.py:15-22` never reads
`currency` from the `info` dict. The peer table in `app/deepdive/valuation_block.py:241`
then computes `_fcf_yield(p.free_cashflow, p.market_cap)`.

The yield itself survives — numerator and denominator are the same currency, so the ratio
is currency-free. But the table sets peers side by side, and a reader comparing a London
peer's absolute figures against a US peer's is comparing pounds with dollars under no
label at all. The margins and growth rates in that table are ratios and stay valid; the
absolute money columns do not.

Note this is *not* fixed by the minor-unit change: after it, a London peer's `market_cap`
is correctly in pounds — it is simply still not dollars.

### (b) `total_debt` / `total_cash` are labelled with the listing currency

`app/deepdive/valuation_block.py:175-176` renders both under `ccy = pit.currency or ""`
(`:102`), i.e. the **listing** currency. But `quant_join.py:116-117` takes them from the
`info` dict, where they follow the issuer's **reporting** currency for the balance-sheet
figures.

The dossier already carries the evidence that these can differ — `quant_join.py:180-181`
emits a `currency_note` exactly when `financialCurrency != currency`, and the EDV.L
dossier says so in plain text: *"Währung: financialCurrency USD != Listing-Währung GBp"*.
So the code knows the two differ and labels the figures anyway.

## Why this was not folded into the minor-unit fix

Different failure classes need different remedies. The minor-unit defect had one true
answer (rescale a curated key set, once, in the adapter) and a mechanical proof
(`marketCap / (price × shares) = 0.0100`). Currency mixing has no single right answer —
it is a product decision:

- convert everything to one presentation currency (needs an FX rate per figure and a
  rate date, and `get_fx_rate` currently only converts *to* EUR);
- or label every money figure with its own currency and refuse to compare across;
- or restrict the peer table to same-currency peers and say why when it cannot.

Bundling that decision into a correctness fix would have made the fix unreviewable.

## Scope (this ticket)

- **Decide the presentation rule first**, before touching code. The three options above
  are genuinely different products; pick one and write down why.
- Give `PeerQuant` a currency field and make `peer_quant.load_peer_quants` populate it —
  that is a prerequisite for every option, and cheap.
- Make `valuation_block` label each money figure with the currency it actually carries,
  rather than with `pit.currency` for all of them. The `currency_note` already computes
  the fact; the renderer just ignores it.
- Decide what the peer table does when peers span currencies: convert, annotate, or
  decline. "Decline and say why" is a legitimate answer and matches how the multi-year
  bands already handle `skipped_fx`.

## Out of scope

- Minor-unit handling — done, see the sibling ticket.
- Any FX-rate sourcing beyond what `YFinanceClient.get_fx_rate` already provides. If the
  chosen rule needs historical or non-EUR rates, that is its own ticket.

## Reproduction

Any dossier for an issuer whose `financialCurrency` differs from `currency`, e.g.
`output/Watchlist/EDV.L_2026-09-03.md` — the `Kapitalstruktur` line labels USD-denominated
debt and cash as the listing currency, and the peer table sets a London issuer beside
three US miners with no currency shown.
