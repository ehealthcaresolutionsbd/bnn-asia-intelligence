"""BNN Asia event taxonomy on top of GDELT/CAMEO codes.

Every rule is public (shown on the methodology page). A GDELT event row is counted in a
signal category when its CAMEO EventCode starts with one of `codes` AND (if given) the
target actor type (Actor2Type1Code) is in `targets` AND (if given) the source actor type
(Actor1Type1Code) is in `perpetrators`.
"""

STATE = {"GOV", "MIL", "COP", "JUD", "SPY"}   # state actors
CIVIC = {"CVL", "OPP", "HRI", "LAB", "EDU", "REL", "NGO", "REF", "MOD", "RAD", "ELI"}
MEDIA = {"MED", "JRN"}

SIGNALS = {
    # key: (label, category slug, CAMEO prefixes, target types, perpetrator types)
    "media_repression": ("Coercion or violence against media/journalists", "press-freedom",
                         ("17", "18", "19", "20"), MEDIA, None),
    "media_arrests": ("Arrests/detentions of media workers", "press-freedom", ("173",), MEDIA, None),
    "state_repression": ("State repression of civilians and civil society", "human-rights",
                         ("175", "173", "174", "18", "19", "20"), CIVIC, STATE),
    "arrests_detentions": ("Arrests and detentions by state actors", "human-rights", ("173",), None, STATE),
    "killings_assaults": ("Killings and physical assaults (all actors)", "human-rights", ("18", "19", "20"), None, None),
    "protests": ("Protest events", "freedom-democracy", ("14",), None, None),
    "protest_repression": ("Repression of protest/opposition", "freedom-democracy", ("175", "1724", "1723"), None, STATE),
    "censorship": ("Bans, restrictions and censorship", "press-freedom", ("172", "1722", "1721"), None, STATE),
    "rule_of_law_cooperation": ("Judicial and legal cooperation events", "rule-of-law", ("061", "0832", "0861"), None, None),
}

# GDELT ActionGeo_CountryCode uses FIPS 10-4. ISO3 → FIPS for BNN's 48 countries.
ISO3_TO_FIPS = {
    "AFG": "AF", "BGD": "BG", "BTN": "BT", "IND": "IN", "MDV": "MV", "NPL": "NP", "PAK": "PK", "LKA": "CE",
    "BRN": "BX", "KHM": "CB", "IDN": "ID", "LAO": "LA", "MYS": "MY", "MMR": "BM", "PHL": "RP", "SGP": "SN",
    "THA": "TH", "TLS": "TT", "VNM": "VM", "CHN": "CH", "JPN": "JA", "MNG": "MG", "PRK": "KN", "KOR": "KS",
    "TWN": "TW", "KAZ": "KZ", "KGZ": "KG", "TJK": "TI", "TKM": "TX", "UZB": "UZ", "BHR": "BA", "IRN": "IR",
    "IRQ": "IZ", "ISR": "IS", "JOR": "JO", "KWT": "KU", "LBN": "LE", "OMN": "MU", "PSE": "WE", "QAT": "QA",
    "SAU": "SA", "SYR": "SY", "TUR": "TU", "ARE": "AE", "YEM": "YM", "ARM": "AM", "AZE": "AJ", "GEO": "GG",
}
EXTRA_FIPS = {"GZ": "PSE"}   # Gaza Strip counted with Palestine
FIPS_TO_ISO3 = {v: k for k, v in ISO3_TO_FIPS.items()} | EXTRA_FIPS

# GDELT v1/v2 event export column positions (58 columns).
COL = {"id": 0, "sqldate": 1, "a1type": 12, "a2type": 22, "event_code": 26, "root": 28, "quad": 29,
       "goldstein": 30, "mentions": 31, "sources": 32, "articles": 33, "tone": 34, "geo_country": 51,
       "dateadded": 56, "url": 57}
