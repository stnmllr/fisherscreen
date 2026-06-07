import scripts.build_universe as bu


# --- mechanism (fixture maps, independent of the real values) ---
def test_remap_then_set_collapses_twin():
    out = bu._apply_symbol_corrections(["BNPP.PA", "BNP.PA", "AAPL"],
                                       corrections={"BNPP.PA": "BNP.PA"}, drop=set())
    assert sorted(set(out)) == ["AAPL", "BNP.PA"]


def test_drop_removes_symbol():
    out = bu._apply_symbol_corrections(["SKY.L", "AAPL"], corrections={}, drop={"SKY.L"})
    assert out == ["AAPL"]


def test_unrelated_untouched():
    out = bu._apply_symbol_corrections(["AAPL", "MSFT"], corrections={"BNPP.PA": "BNP.PA"}, drop=set())
    assert out == ["AAPL", "MSFT"]


def test_idempotent():
    corr = {"BNPP.PA": "BNP.PA"}
    once = bu._apply_symbol_corrections(["BNPP.PA", "BNP.PA"], corrections=corr, drop=set())
    twice = bu._apply_symbol_corrections(once, corrections=corr, drop=set())
    assert sorted(set(once)) == sorted(set(twice))


# --- invariants on the REAL constants (from GATE-1 table) ---
def test_corrections_are_injective():
    values = list(bu.SYMBOL_CORRECTIONS.values())
    assert len(values) == len(set(values)), "duplicate correction targets"


def test_key_is_not_its_own_value():
    for k, v in bu.SYMBOL_CORRECTIONS.items():
        assert k != v


def test_drop_and_corrections_disjoint():
    assert not (set(bu.SYMBOL_CORRECTIONS) & bu.SYMBOL_DROP)


def test_known_contaminants_resolved():
    for bad in ["BNPP.PA", "SASY.PA", "SOGN.PA", "SGOB.PA", "BOUY.PA", "ENX.AS",
                "CTS.DE", "SGEF.PA", "DANO.PA", "CARR.PA", "ATOS.PA", "FTI.L"]:
        assert bad in bu.SYMBOL_CORRECTIONS or bad in bu.SYMBOL_DROP, bad
    assert "LII.L" in bu.SYMBOL_DROP and "SKY.L" in bu.SYMBOL_DROP
