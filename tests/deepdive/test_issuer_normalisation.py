"""Issuer-name normalisation: the counter-basket, the stump survey, one case
per rule.

The change under test rebuilt the normalisation on BOTH sides of the issuer
comparison so that 147 of 416 EU tickers stop failing. Nothing was loosened —
prefix tolerance was measured at +12.6 points and rejected, because it accepts
ROCHE HOLDING AG as ROCHE BOBOIS. That decision is what makes THIS module the
load-bearing one: with the comparison still strict, the only way a wrong match
can now happen is that normalisation shrinks two different names into the same
generic stump. The counter-basket and the stump survey below are the two
instruments against exactly that, and they come first for that reason; the
per-rule cases after them document why each rule exists.

Every name in this file is real. The provenance is the yfinance ticker in the
parametrisation id or comment, from the offline corpus measured on 2026-09-04
(`cache/identity_name_corpus.json`) or from the census over all 416 dotted EU
tickers. `cache/` is gitignored, so names are copied in as literals rather than
read at run time — see tests/deepdive/issuer_name_survey.py.
"""

import collections
from unittest.mock import MagicMock

import pytest

from app.deepdive.eu_adr_resolution import (
    find_home_identity,
    issuer_name,
    issuer_tokens,
    norm_issuer,
    same_issuer_identity,
)
from tests.deepdive.issuer_name_survey import NAMES, SAME_COMPANY_ALIASES, issuer_of

# ---------------------------------------------------------------------------
# 1. The counter-basket: three pairs that must never match.
#
# All three were observed for real. The first is the documented variant-ladder
# false hit that strict equality was introduced against; the other two are
# data-source errors where the name check correctly refused, and both got an
# override row in data/adr_table.json instead of a matcher concession.
# ---------------------------------------------------------------------------

_COUNTER_BASKET = (
    pytest.param(
        "ROG.SW",
        "ROCHE HOLDING AG",
        "ROCHE BOBOIS SA-UNSPON ADR",
        id="roche_holding_is_not_roche_bobois",
    ),
    pytest.param(
        "BT-A.L",
        "BT Group plc",
        "BRITANNIA GROUP PLC",
        id="bt_group_is_not_britannia_group",
    ),
    pytest.param(
        "GLB.IR",
        "Beacon Hill CBO III Ltd",
        "GLANBIA PLC",
        id="beacon_hill_is_not_glanbia",
    ),
)


@pytest.mark.parametrize("ticker,reference,openfigi_answer", _COUNTER_BASKET)
def test_counter_basket_pair_is_refused_by_the_real_comparison_path(
    ticker, reference, openfigi_answer
):
    """THE guard, asserted where production actually decides.

    Deliberately not a call to `same_issuer_identity`: the property that must
    hold is that `find_home_identity` refuses these answers, and a future
    refactor that compares names some other way — or forgets to compare them at
    all — has to fail here. Checking the helper alone could stay green while the
    caller stopped consulting it.

    `map_ticker.called` is asserted too: without it the test would also pass if
    the ladder had silently become empty, i.e. for the wrong reason. What is
    being pinned is that OpenFIGI ANSWERED and the answer was rejected."""
    openfigi = MagicMock()
    openfigi.map_ticker.return_value = {
        "name": openfigi_answer,
        "shareClassFIGI": "BBG001SCOUNTER",
    }

    ident = find_home_identity(ticker, reference, openfigi=openfigi)

    assert ident is None
    assert openfigi.map_ticker.called


@pytest.mark.parametrize("ticker,left,right", _COUNTER_BASKET)
def test_counter_basket_pair_is_not_the_same_issuer_in_either_direction(
    ticker, left, right
):
    """Same three pairs one level down, and symmetric on purpose: the two sides
    of the comparison are a yfinance name and an OpenFIGI name, and which one
    arrives as which argument is an accident of the call site. An asymmetric
    matcher would be a latent false hit waiting for the arguments to swap."""
    assert same_issuer_identity(left, right) is False
    assert same_issuer_identity(right, left) is False


def test_prefix_tolerance_would_accept_roche_bobois_and_is_therefore_absent():
    """The measured fact behind "no prefix tolerance", kept executable.

    This assertion inherits from the deleted characterisation test of
    `_same_issuer` (removed with the function itself): 'ROCHE HOLDING AG'
    normalises to plain 'ROCHE' — HOLDING is a legal form — and 'ROCHE' IS a
    prefix of 'ROCHEBOBOIS'. So a prefix-tolerant comparison accepts the
    documented false hit, which is why the +12.6 points it was measured at were
    declined. Strict equality is the ONLY thing standing between the variant
    ladder and Roche Bobois; there is no second line of defence below it.

    Anyone tempted to loosen `same_issuer_identity` must make this test fail
    first, which is the point of writing it down as code rather than prose."""
    roche, bobois = norm_issuer("ROCHE HOLDING AG"), norm_issuer("ROCHE BOBOIS SA")

    assert roche == "ROCHE"
    assert bobois.startswith(roche)  # what prefix tolerance would accept
    assert same_issuer_identity("ROCHE HOLDING AG", "ROCHE BOBOIS SA") is False


def test_token_multiset_arm_does_not_accept_a_superset_of_the_tokens():
    """The order-insensitive arm compares MULTISETS, not subsets — the one
    loosening in this change, fenced at its own edge. ('ROCHE',) against
    ('ROCHE', 'BOBOIS') is precisely the shape a subset rule would accept."""
    assert issuer_tokens("ROCHE HOLDING AG") == ("ROCHE",)
    assert issuer_tokens("ROCHE BOBOIS SA-UNSPON ADR") == ("ROCHE", "BOBOIS")
    assert same_issuer_identity("ROCHE HOLDING AG", "ROCHE BOBOIS SA-UNSPON ADR") is (
        False
    )


# ---------------------------------------------------------------------------
# 2. The substring-stump regression.
#
# A REAL PRE-EXISTING BUG, fixed along the way: the old `norm_issuer` removed
# legal forms as SUBSTRINGS, so ' AG' matched inside ' AGRICOLE' and
# 'CREDIT AGRICOLE SA' became 'CREDITRICOLE'. Legal forms are now removed at
# token boundaries only. The defect was silent — a stump still compares equal
# to itself, so both sides mangled the same way still matched and nobody looked.
# It is pinned here for every affected shape found in the corpus, not only for
# the documented one.
# ---------------------------------------------------------------------------

_SUBSTRING_STUMPS = (
    pytest.param(
        "CREDIT AGRICOLE SA",
        ("CREDIT", "AGRICOLE"),
        "CREDITRICOLE",
        id="ACA_PA_ag_inside_agricole",
    ),
    pytest.param(
        "J Sainsbury plc",
        ("J", "SAINSBURY"),
        "JINSBURY",
        id="SBRY_L_sa_inside_sainsbury",
    ),
    pytest.param(
        "BANCO SANTANDER SA",
        ("BANCO", "SANTANDER"),
        "BANCONTANDER",
        id="SAN_MC_sa_inside_santander",
    ),
    pytest.param(
        "LEROY SEAFOOD GROUP ASA",
        ("LEROY", "SEAFOOD"),
        "LEROYAFOOD",
        id="LSG_OL_se_inside_seafood",
    ),
    pytest.param(
        "The Sage Group plc",
        ("THE", "SAGE"),
        "THEGE",
        id="SGE_L_sa_inside_sage",
    ),
    pytest.param(
        "INTESA SANPAOLO",
        ("INTESA", "SANPAOLO"),
        "INTESANPAOLO",
        id="ISP_MI_sa_inside_sanpaolo",
    ),
)


@pytest.mark.parametrize("name,expected_tokens,old_stump", _SUBSTRING_STUMPS)
def test_a_legal_form_inside_a_word_is_not_removed(name, expected_tokens, old_stump):
    """Both halves are asserted, and both are needed.

    The token equality says what the name normalises TO — a positive statement
    that a later rule change cannot satisfy by accident. The inequality names
    the exact stump the old substring rule produced, so the regression is
    recognisable by the reader and by `git log` alike; a bare "is not mangled"
    would leave nothing to compare against the next time someone reaches for
    `str.replace`."""
    assert issuer_tokens(name) == expected_tokens
    assert norm_issuer(name) != old_stump


def test_the_two_spellings_of_credit_agricole_still_meet_after_the_fix():
    """The fix must not cost the match it was blocking. ACA.PA is the documented
    case: yfinance writes 'Crédit Agricole S.A.', OpenFIGI 'CREDIT AGRICOLE SA',
    and the two only meet once the accent and the dots are folded AND the ' AG'
    inside 'AGRICOLE' is left alone. Under the old rule both sides mangled to
    the same stump and matched anyway — which is exactly why the bug survived
    for years."""
    assert same_issuer_identity("Crédit Agricole S.A.", "CREDIT AGRICOLE SA") is True
    assert norm_issuer("Crédit Agricole S.A.") == "CREDITAGRICOLE"


def test_a_legal_form_in_the_middle_of_a_name_survives():
    """The other half of the boundary rule, and the reason it is EDGES and not
    merely tokens: 'GROUP' is a legal form at the end of 'BT Group plc', but in
    'ERSTE GROUP BANK AG' it sits in the middle and belongs to the name.
    Removing it there would produce ERSTEBANK, a different bank's plausible
    stump. (EBS.VI, census 2026-09-04.)"""
    assert issuer_tokens("ERSTE GROUP BANK AG") == ("ERSTE", "GROUP", "BANK")


# ---------------------------------------------------------------------------
# 3. The stump survey, as a test.
#
# Run once as a script over 385 real names and reported in the PR text as the
# spec requires; frozen here so it keeps its meaning. Its single job: the
# normalisation must not shrink two DIFFERENT issuers to the same identity.
# ---------------------------------------------------------------------------


def _identity_keys(name: str) -> tuple[tuple[str, ...], ...]:
    """The two keys under which `same_issuer_identity` can declare a match: the
    token sequence and the token multiset."""
    tokens = issuer_tokens(name)
    return tokens, tuple(sorted(tokens))


def test_no_two_different_issuers_normalise_to_the_same_identity():
    """THE survey. 385 real names, 305 distinct companies, zero collisions.

    Bucketed by key rather than compared pairwise: both arms of
    `same_issuer_identity` are equality on a derived key, so "some pair matches"
    and "some bucket holds two issuers" are the same statement — at O(n) instead
    of O(n²), and with a failure message that names the colliding issuers
    instead of one arbitrary pair.

    The one exception the survey found is not a collision at all and is
    recorded, with its reasoning, in `SAME_COMPANY_ALIASES`: RNL.PA and RNO.PA
    are two Yahoo symbols for Renault SA."""
    issuers_by_key: dict[tuple[str, ...], set[str]] = collections.defaultdict(set)
    for ticker, name in NAMES:
        for key in _identity_keys(name):
            issuers_by_key[key].add(issuer_of(ticker))

    collisions = {
        "".join(key): sorted(issuers)
        for key, issuers in issuers_by_key.items()
        if len(issuers) > 1
    }

    assert not collisions, (
        f"normalisation shrank different issuers onto a shared stump: "
        f"{collisions}. Either the name table gained two spellings of ONE "
        f"company (then record it in SAME_COMPANY_ALIASES), or a rule became "
        f"too aggressive — in which case introduce a minimum length after "
        f"normalisation and refuse to match below it (spec §5)."
    )


def test_no_survey_name_normalises_to_nothing():
    """The precondition that makes the bucketing above equivalent to the real
    comparison. `same_issuer_identity` refuses an empty side outright, so two
    names that both normalised to () would share a bucket without ever
    matching — the survey would report a collision that is not one. It would
    also be a defect in its own right: a name reduced to nothing is the extreme
    stump."""
    empty = sorted({name for _, name in NAMES if not issuer_tokens(name)})
    assert not empty


def test_the_survey_still_has_the_breadth_it_claims():
    """FIXTURE INTEGRITY. The survey proves an absence, and an absence gets
    cheaper the smaller the input: a table quietly trimmed to a handful of names
    would stay green and stop meaning anything. Pinned as exact counts, so
    ADDING names is a deliberate act (update the numbers) and losing them is
    impossible to do silently."""
    assert len(NAMES) == 385
    assert len({issuer_of(ticker) for ticker, _ in NAMES}) == 305


def test_every_same_company_alias_records_a_collision_that_really_happens():
    """An alias is an EXCUSE for a collision, so the excuses must stay honest.
    A dead entry — one whose two tickers no longer collide — would be a
    ready-made hiding place: someone adds a name that collides with it, and the
    survey stays green because the pair is already forgiven. Each alias must
    therefore still point at a real, currently-occurring match."""
    for alias, canonical in SAME_COMPANY_ALIASES.items():
        alias_names = [name for ticker, name in NAMES if ticker == alias]
        canonical_names = [name for ticker, name in NAMES if ticker == canonical]
        assert alias_names, f"{alias} contributes no name to the survey"
        assert canonical_names, f"{canonical} contributes no name to the survey"
        assert any(
            same_issuer_identity(left, right)
            for left in alias_names
            for right in canonical_names
        ), (
            f"the alias {alias} -> {canonical} no longer describes a collision; "
            f"delete it rather than leave a standing excuse behind"
        )


def test_the_shortest_stumps_in_the_survey_are_the_five_known_two_letter_ones():
    """The spec asks for the shortest normalised names to be looked at once.
    This is that look, frozen: five two-letter stumps, each belonging to a
    company whose name genuinely is two letters, and none of them shared. Two
    characters is still enough for STRICT equality — the survey above proves
    they collide with nothing — but they are the first place a future rule
    would do damage, so the set is pinned rather than a minimum length asserted.

    A new entry here means a name got shorter than any real EU issuer name is,
    and is worth a human look before it is added to the list."""
    two_letter = {norm_issuer(name) for _, name in NAMES if len(norm_issuer(name)) <= 2}
    assert two_letter == {"3I", "BT", "IG", "MG", "NN"}


# ---------------------------------------------------------------------------
# 4. One case per rule, each drawn from the corpus.
#
# These are the pairs that used to fail. Each row is a measured yfinance name
# against the measured OpenFIGI name of the SAME ticker, so the row documents
# both what the rule does and why it had to exist.
# ---------------------------------------------------------------------------

_MATCHING_PAIRS = (
    # Rule 1 — transliteration. Ø is a letter in its own right: NFKD does not
    # decompose it, so without the table the ASCII filter drops it silently and
    # 'Ørsted' becomes 'RSTED'.
    pytest.param(
        "Ørsted A/S", "ORSTED A/S", "ORSTED", id="ORSTED_CO_transliterate_o_slash"
    ),
    pytest.param(
        "Lerøy Seafood Group ASA",
        "LEROY SEAFOOD GROUP ASA",
        "LEROYSEAFOOD",
        id="LSG_OL_transliterate_lowercase_o_slash",
    ),
    # Rule 2 — diacritics via NFKD. Cheap, and the half of the alphabet the
    # table above deliberately does not cover.
    pytest.param(
        "Meliá Hotels International, S.A.",
        "MELIA HOTELS INTERNATIONAL",
        "MELIAHOTELSINTERNATIONAL",
        id="MEL_MC_acute_accent",
    ),
    pytest.param(
        "Industria de Diseño Textil, S.A.",
        "INDUSTRIA DE DISENO TEXTIL",
        "INDUSTRIADEDISENOTEXTIL",
        id="ITX_MC_tilde",
    ),
    pytest.param(
        "Nestlé S.A.", "NESTLE SA-REG", "NESTLE", id="NESN_SW_accent_and_descriptor"
    ),
    # Rule 3 — punctuation, the second-largest measured gain (+17.7 points).
    # Dots and apostrophes vanish INSIDE a token rather than splitting it, which
    # is what lets 'S.M.E.' meet 'SME' and "JAMES'S" meet "JAMES'S".
    pytest.param(
        "St. James's Place plc",
        "ST JAMES'S PLACE PLC",
        "STJAMESSPLACE",
        id="STJ_L_dots_and_apostrophes",
    ),
    pytest.param(
        "Aena S.M.E., S.A.", "AENA SME SA", "AENASME", id="AENA_MC_dotted_initialism"
    ),
    pytest.param("L'Oréal S.A.", "L'OREAL", "LOREAL", id="OR_PA_apostrophe_and_accent"),
    # Rule 4 — spelled-out legal forms, the largest measured gain (+24.0 points)
    # and effectively the whole German and French half of the corpus.
    pytest.param(
        "Bayer Aktiengesellschaft",
        "BAYER AG-REG",
        "BAYER",
        id="BAYN_DE_aktiengesellschaft",
    ),
    pytest.param(
        "Société Générale Société anonyme",
        "SOCIETE GENERALE SA",
        "SOCIETEGENERALE",
        id="GLE_PA_societe_anonyme",
    ),
    pytest.param(
        "Hermès International Société en commandite par actions",
        "HERMES INTERNATIONAL",
        "HERMESINTERNATIONAL",
        id="RMS_PA_societe_en_commandite_par_actions",
    ),
    pytest.param(
        "Galp Energia, SGPS, S.A.",
        "GALP ENERGIA SGPS SA",
        "GALPENERGIA",
        id="GALP_LS_sgps",
    ),
    pytest.param(
        "British American Tobacco p.l.c.",
        "BRITISH AMERICAN TOBACCO PLC",
        "BRITISHAMERICANTOBACCO",
        id="BATS_L_plc_with_dots",
    ),
    pytest.param(
        "OC Oerlikon Corporation AG",
        "OC OERLIKON CORP AG-REG",
        "OCOERLIKON",
        id="OERL_SW_corporation_against_corp",
    ),
    pytest.param("Tele2 AB (publ)", "TELE2 AB-B SHS", "TELE2", id="TEL2_B_ST_publ"),
    # Rule 5 — LEADING legal forms. Scandinavian names carry them in front,
    # where the old trailing-only catalogue never looked.
    pytest.param("AB SKF (publ)", "SKF AB-B SHARES", "SKF", id="SKF_B_ST_leading_ab"),
    pytest.param(
        "AB Volvo (publ)", "VOLVO AB-B SHS", "VOLVO", id="VOLV_B_ST_leading_ab"
    ),
    # Rule 6 — the descriptor allow-list, replacing the "-TOKEN without a space"
    # heuristic. A share-class marker is stripped in every layout OpenFIGI
    # writes it in: attached to a hyphen, spelled with a class word, spaced out.
    pytest.param(
        "Atlas Copco AB (publ)",
        "ATLAS COPCO AB-A SHS",
        "ATLASCOPCO",
        id="ATCO_A_ST_hyphenated_class_letter",
    ),
    pytest.param(
        "Swedbank AB (publ)",
        "SWEDBANK AB - A SHARES",
        "SWEDBANK",
        id="SWED_A_ST_spaced_class_letter",
    ),
    pytest.param(
        "Stora Enso Oyj", "STORA ENSO OYJ-R SHS", "STORAENSO", id="STERV_HE_r_shares"
    ),
    pytest.param(
        "Carl Zeiss Meditec AG",
        "CARL ZEISS MEDITEC AG - BR",
        "CARLZEISSMEDITEC",
        id="AFX_DE_spaced_bearer_descriptor",
    ),
    # Rule 7 — yfinance's own LSE listing descriptors. The reference side needs
    # the same treatment as the OpenFIGI side; that symmetry is the design.
    pytest.param("3i Group Ord", "3I GROUP PLC", "3I", id="III_L_trailing_ord"),
)


@pytest.mark.parametrize("reference,line,expected_key", _MATCHING_PAIRS)
def test_the_two_spellings_of_one_issuer_meet(reference, line, expected_key):
    """Both sides land on the SAME stated key, and only then does the match
    count. Asserting `same_issuer_identity` alone would also pass if a rule ever
    collapsed both sides to something far too generic — the key is what says
    which company the pair is agreed to be."""
    assert norm_issuer(reference) == expected_key
    assert norm_issuer(line) == expected_key
    assert same_issuer_identity(reference, line) is True


# The order-insensitive arm gets its own table: for these pairs the two sides do
# NOT produce the same key, and that is the whole point — OpenFIGI files the
# surname first ('FISCHER (GEORG)'), yfinance does not. Word order is the one
# difference between the sources that carries no information.
_WORD_ORDER_PAIRS = (
    pytest.param(
        "Georg Fischer AG",
        "FISCHER (GEORG)-REG",
        ("GEORG", "FISCHER"),
        ("FISCHER", "GEORG"),
        id="GF_SW_surname_first",
    ),
    pytest.param(
        "J Sainsbury plc",
        "SAINSBURY (J) PLC",
        ("J", "SAINSBURY"),
        ("SAINSBURY", "J"),
        id="SBRY_L_initial_moved_behind_the_name",
    ),
    pytest.param(
        "Telefonaktiebolaget LM Ericsson (publ)",
        "ERICSSON LM-B SHS",
        ("LM", "ERICSSON"),
        ("ERICSSON", "LM"),
        id="ERIC_B_ST_leading_form_plus_swapped_order",
    ),
)


@pytest.mark.parametrize(
    "reference,line,reference_tokens,line_tokens", _WORD_ORDER_PAIRS
)
def test_swapped_word_order_matches_through_the_multiset_arm(
    reference, line, reference_tokens, line_tokens
):
    """The strict key inequality is asserted first and is not decoration: it is
    what proves the multiset arm — and not some accidental collapse of the two
    names — is carrying the match."""
    assert issuer_tokens(reference) == reference_tokens
    assert issuer_tokens(line) == line_tokens
    assert norm_issuer(reference) != norm_issuer(line)
    assert same_issuer_identity(reference, line) is True


def test_a_single_letter_that_is_not_a_share_class_stays_in_the_name():
    """The edge the class-letter rule has to get right, and the reason it reads
    layout instead of just length: the J of 'SAINSBURY (J) PLC' is J Sainsbury's
    name, while the B of 'ASSA ABLOY AB-B' is a share class. Drop the first and
    the issuer becomes 'SAINSBURY'; keep the second and the two spellings of
    Assa Abloy never meet."""
    assert issuer_tokens("SAINSBURY (J) PLC") == ("SAINSBURY", "J")
    assert issuer_tokens("ASSA ABLOY AB-B") == ("ASSA", "ABLOY")
    assert same_issuer_identity("ASSA ABLOY AB (publ)", "ASSA ABLOY AB-B") is True


def test_air_france_klm_is_not_truncated_at_its_hyphen():
    """THE DEFECT the descriptor allow-list replaced. The old rule stripped a
    trailing '-TOKEN' whenever the token held no space, which turned
    'AIR FRANCE-KLM' into 'AIR FRANCE' — a different airline group, and one
    that would then have failed to match its own reference name. Its docstring
    justified the heuristic with 'COCA-COLA CO', which it survives only by
    accident (the token behind the hyphen there happens to contain a space).

    KLM is kept because the allow-list simply does not contain it, which is the
    difference between a positive list and a guess about string shape."""
    assert issuer_tokens("AIR FRANCE-KLM") == ("AIR", "FRANCE", "KLM")
    assert issuer_name("AIR FRANCE-KLM") == "AIR FRANCE-KLM"
    assert same_issuer_identity("Air France-KLM SA", "AIR FRANCE-KLM") is True


# ---------------------------------------------------------------------------
# 5. yfinance listing descriptors and the nominal-value tail.
# ---------------------------------------------------------------------------

_LISTING_DESCRIPTOR_NAMES = (
    pytest.param("3i Group Ord", "3I GROUP PLC", "3I", id="III_L_ord"),
    pytest.param(
        "ANTOFAGASTA PLC ORD 5P",
        "Antofagasta plc",
        "ANTOFAGASTA",
        id="ANTO_L_ord_with_nominal_value",
    ),
    pytest.param(
        "WISE GROUP PLC CLS A ORD USD0.0",
        "WISE GROUP PLC-CL A",
        "WISE",
        id="WISE_L_class_and_nominal_value",
    ),
)


@pytest.mark.parametrize(
    "yfinance_name,other_spelling,expected_key", _LISTING_DESCRIPTOR_NAMES
)
def test_lse_listing_descriptors_are_stripped_from_the_reference_side(
    yfinance_name, other_spelling, expected_key
):
    """Measured yfinance names for LSE titles (spec §1.7, 2026-09-04). The
    descriptors say WHICH LINE this is, never WHICH COMPANY, so they have to go
    on the reference side as well — otherwise every LSE title fails against an
    OpenFIGI name that never carried them."""
    assert norm_issuer(yfinance_name) == expected_key
    assert same_issuer_identity(yfinance_name, other_spelling) is True


def test_the_nominal_value_rule_does_not_eat_the_3i_of_3i_group():
    """The trap in the nominal-value tail. '5P' and 'USD0.0' are letters-plus-
    digits and so is '3I' — matching that pattern anywhere would leave '3i
    Group Ord' with nothing at all. The tail is only cut behind an introducer
    ('ORD', 'SHS', 'SHARES'), so a leading '3I' is never a candidate."""
    assert norm_issuer("3i Group Ord") == "3I"
    assert norm_issuer("3I GROUP PLC") == "3I"


# ---------------------------------------------------------------------------
# 6. `issuer_name` — the human-readable identity used for logs and notes.
# ---------------------------------------------------------------------------

_ISSUER_NAMES = (
    pytest.param("ROCHE HOLDING AG-BR", "ROCHE HOLDING AG", id="bearer_descriptor"),
    pytest.param(
        "CARL ZEISS MEDITEC AG - BR",
        "CARL ZEISS MEDITEC AG",
        id="spaced_descriptor_leaves_no_dangling_hyphen",
    ),
    pytest.param(
        "WISE GROUP PLC CLS A ORD USD0.0", "WISE GROUP PLC", id="class_and_ord"
    ),
    pytest.param("3i Group Ord", "3I GROUP", id="yfinance_ord"),
    pytest.param("COCA-COLA CO", "COCA-COLA CO", id="hyphen_belonging_to_the_name"),
    pytest.param("AIR FRANCE-KLM", "AIR FRANCE-KLM", id="the_truncation_defect"),
    pytest.param("SAINSBURY (J) PLC", "SAINSBURY (J) PLC", id="initial_is_not_a_class"),
    pytest.param("GECINA", "GECINA", id="nothing_to_strip"),
)


@pytest.mark.parametrize("figi_name,expected", _ISSUER_NAMES)
def test_issuer_name_strips_only_listing_descriptors(figi_name, expected):
    """Legal forms STAY — this output is for reading, not for comparing. The
    result is a cut of the original string rather than rejoined tokens, which is
    why the punctuation inside 'COCA-COLA CO' survives while the ' - ' before a
    stripped descriptor does not."""
    assert issuer_name(figi_name) == expected


def test_issuer_name_and_norm_issuer_cannot_drift_apart():
    """`norm_issuer(issuer_name(x)) == norm_issuer(x)`, over every name in the
    survey. Older diagnostics normalise in two steps, production in one; the day
    the two disagree, a name matches in one call site and not in the other, and
    nothing else in the suite would notice."""
    drifted = [
        name for _, name in NAMES if norm_issuer(issuer_name(name)) != norm_issuer(name)
    ]
    assert not drifted


# ---------------------------------------------------------------------------
# 7. Degenerate input: the guards that keep "reduced to nothing" from matching.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "left,right",
    [
        pytest.param("", "", id="both_empty"),
        pytest.param("ROCHE HOLDING AG", "", id="one_side_empty"),
        pytest.param("", "ROCHE HOLDING AG", id="other_side_empty"),
        pytest.param("&&&", "&&&", id="punctuation_only"),
        pytest.param("   ", "\t", id="whitespace_only"),
    ],
)
def test_a_name_that_normalises_to_nothing_never_matches(left, right):
    """Not even itself. An empty key is the ultimate stump: every name that
    folds away would otherwise be the same issuer as every other, and yfinance
    does hand out unusable names (that is what the GLB.IR override exists for).
    Refusing is `unverifiable_identity`, which is the honest verdict."""
    assert same_issuer_identity(left, right) is False


def test_a_name_consisting_only_of_a_legal_form_keeps_it():
    """The emptiness guard inside the legal-form stripper, from the other side:
    stripping is skipped when it would consume the whole name. Returning ''
    would make every such name equal to every other — and this is the one place
    the rule can produce an empty result at all."""
    assert norm_issuer("PLC") == "PLC"
    assert norm_issuer("AG") == "AG"
    assert same_issuer_identity("PLC", "AG") is False
