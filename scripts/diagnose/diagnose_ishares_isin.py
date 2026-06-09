"""Throwaway verify probe (round 4): for the proposed RIC->Yahoo candidate map,
confirm each candidate resolves as EQUITY, its longName agrees with the
provenance-native Wikipedia Company (legal-suffix-stripped), and its exchange/
country is plausible. Flags mismatches for review. $0, network."""
import re

from app.errors import DataSourceError, DegradedDataError
from app.services.yfinance_client import YFinanceClientImpl

# RIC contaminant -> proposed Yahoo candidate (Company from build-date Wikipedia revision)
PROPOSED = {
    "AIRP.PA": ("AI.PA", "Air Liquide"),
    "ATOS.PA": ("ATO.PA", "Atos"),
    "BNPP.PA": ("BNP.PA", "BNP Paribas"),
    "BOUY.PA": ("EN.PA", "Bouygues"),
    "CAGR.PA": ("ACA.PA", "Credit Agricole"),
    "CAPP.PA": ("CAP.PA", "Capgemini"),
    "CARR.PA": ("CA.PA", "Carrefour"),
    "CTS.DE": ("EVD.DE", "CTS Eventim"),
    "DANO.PA": ("BN.PA", "Danone"),
    "ENX.AS": ("ENX.PA", "Euronext"),
    "MICP.PA": ("ML.PA", "Michelin"),
    "OREP.PA": ("OR.PA", "L'Oreal"),
    "PERP.PA": ("RI.PA", "Pernod Ricard"),
    "RENA.PA": ("RNO.PA", "Renault"),
    "SASY.PA": ("SAN.PA", "Sanofi"),
    "SCHN.PA": ("SU.PA", "Schneider Electric"),
    "SGEF.PA": ("DG.PA", "Vinci"),
    "SGOB.PA": ("SGO.PA", "Saint-Gobain"),
    "SOGN.PA": ("GLE.PA", "Societe Generale"),
    "FTI.L": ("FTI", "TechnipFMC"),  # twin-collapse onto existing NYSE listing
}
DROP = {"LII.L": "Liberty Global (LII=Lennox, different co.)", "SKY.L": "Sky Group (delisted 2018)"}

_LEGAL = re.compile(r"\b(s\.?a\.?|se|plc|ag|n\.?v\.?|sa/nv|group|groupe|co|inc|ltd|"
                    r"holding|holdings|the|company|ord|spa|s\.?p\.?a\.?)\b", re.I)


def _norm(name: str) -> str:
    name = (name or "").lower()
    name = name.replace("é", "e").replace("è", "e").replace("ê", "e").replace("ï", "i").replace("ô", "o")
    name = _LEGAL.sub(" ", name)
    return re.sub(r"[^a-z0-9]+", " ", name).strip()


def _agrees(wiki: str, yf_name: str) -> bool:
    a, b = _norm(wiki), _norm(yf_name)
    if not a or not b:
        return False
    return a in b or b in a


def main() -> None:
    client = YFinanceClientImpl()
    print(f"{'RIC':10} {'->cand':9} {'quoteType':10} {'exch':8} {'agree':6} longName")
    for ric, (cand, wiki) in PROPOSED.items():
        try:
            info = client.get_ticker_info(cand)
        except (DataSourceError, DegradedDataError) as exc:
            print(f"{ric:10} {cand:9} ERROR: {exc}")
            continue
        qt = info.get("quoteType")
        exch = info.get("exchange") or info.get("fullExchangeName") or "?"
        ln = info.get("longName") or info.get("shortName") or ""
        ok = (qt == "EQUITY") and _agrees(wiki, ln)
        flag = "OK" if ok else "REVIEW"
        print(f"{ric:10} {cand:9} {str(qt):10} {str(exch):8} {flag:6} {ln}  (wiki={wiki})")
    print("\nDROP:")
    for t, why in DROP.items():
        print(f"  {t}: {why}")


if __name__ == "__main__":
    main()
