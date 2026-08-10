"""Resolve an English manufacturer from a Korean-auction model/name string.

Lotte's listing rows carry no maker column — only a model string such as
``"EV6 (E) 롱레인지 에어 2WD"`` or ``"THE NEW GRANDEUR (H) 2.4 프리미엄"``. The
parser previously "extracted" the brand by scanning that string for a hardcoded
list which, despite its name, held *model* names: a Kia Sorento came back with
``brand="SORENTO"``, a Hyundai Grandeur with ``brand="GRANDEUR"``, and anything
outside the list (EV6, Palisade) with ``brand="UNKNOWN"``. The Hyundai/Kia
mapping that followed was unreachable — the loop above it always returned first.

This is a direct port of ``lib/utils/resolveManufacturer.ts`` in the frontend,
which was written to paper over exactly that bug at display time. Keeping one
mapping in two languages is a real cost, but the alternative — the API serving
a value every client has to correct — is worse, and porting it verbatim means
the two cannot disagree about a given car.

Brand names are always rendered in English in every locale (project rule), so
this returns a single English string. Casing matches the frontend exactly.
"""

from __future__ import annotations

import re
from typing import Optional


# brand -> model keywords that identify it. Order here is for readability only;
# matching below is longest-keyword-first so "SANTA FE" wins over "SANTA".
RULES: dict[str, tuple[str, ...]] = {
    "Genesis": ("G70", "G80", "G90", "GV60", "GV70", "GV80", "EQ900"),
    "Hyundai": (
        "AVANTE", "ELANTRA", "SONATA", "GRANDEUR", "AZERA", "EQUUS", "ACCENT",
        "VERNA", "SANTAFE", "SANTA FE", "MAXCRUZ", "VERACRUZ", "TUCSON", "KONA",
        "VENUE", "PALISADE", "NEXO", "IONIQ", "CASPER", "STARIA", "STAREX",
        "VELOSTER", "GALLOPER", "TERRACAN", "TRAJET", "MATRIX", "GETZ", "ATOS",
        "PONY", "EXCEL", "GRACE", "PORTER", "SOLATI", "MIGHTY", "COUNTY",
        "AEROTOWN", "AEROCITY", "I30", "I40",
    ),
    "Kia": (
        "MORNING", "PICANTO", "RAY", "K3", "K5", "K7", "K8", "K9", "FORTE",
        "CERATO", "OPTIMA", "CADENZA", "STINGER", "SPORTAGE", "SORENTO",
        "MOHAVE", "BORREGO", "CARNIVAL", "SEDONA", "SELTOS", "STONIC", "NIRO",
        "SOUL", "TELLURIDE", "CARENS", "RONDO", "CEED", "RIO", "PRIDE",
        "SPECTRA", "SEPHIA", "SHUMA", "VISTO", "RETONA", "OPIRUS", "POTENTIA",
        "BONGO", "PREGIO", "TOWNER", "K2500", "K2700", "K3000", "K4000",
        "ENTERPRISE", "EV6", "EV9",
    ),
    "Chevrolet": (
        "SPARK", "MATIZ", "CRUZE", "LACETTI", "AVEO", "GENTRA", "KALOS",
        "LANOS", "NUBIRA", "MALIBU", "TOSCA", "MAGNUS", "LEGANZA", "EPICA",
        "ALPHEON", "IMPALA", "EQUINOX", "CAPTIVA", "WINSTORM", "ORLANDO",
        "TRAILBLAZER", "TRAVERSE", "DAMAS", "LABO", "REZZO", "TACUMA", "TICO",
        "VERITAS", "STATESMAN", "CAMARO", "COLORADO", "TRAX", "BOLT",
    ),
    "Renault Korea": (
        "SM3", "SM5", "SM6", "SM7", "QM3", "QM5", "QM6", "XM3", "KOLEOS",
        "GRAND KOLEOS", "LATITUDE", "CLIO", "CAPTUR", "TWIZY", "MASTER",
        "ARKANA", "SCALA", "FLUENCE",
    ),
    "KG Mobility": (
        "KORANDO", "TIVOLI", "REXTON", "ACTYON", "KYRON", "RODIUS", "TORRES",
        "MUSSO", "CHAIRMAN", "ISTANA",
    ),
    # Imported makes — Lotte spells the make out in the model string
    # ("BMW 523D", "BENZ E ...", "JEEP GRAND CHEROKEE", "TESLA MODEL 3").
    "MINI": ("MINI",),
    "BMW": ("BMW",),
    "Mercedes-Benz": ("MERCEDES", "BENZ", "MAYBACH", "AMG"),
    "Audi": ("AUDI",),
    "Volkswagen": ("VOLKSWAGEN", "TIGUAN", "TOUAREG", "ARTEON"),
    "Volvo": ("VOLVO",),
    "Porsche": (
        "PORSCHE", "CAYENNE", "PANAMERA", "MACAN", "TAYCAN", "CAYMAN", "BOXSTER",
    ),
    "Land Rover": (
        "LAND ROVER", "RANGE ROVER", "RANGEROVER", "DISCOVERY", "DEFENDER",
        "EVOQUE", "VELAR", "FREELANDER",
    ),
    "Jaguar": ("JAGUAR",),
    "Jeep": (
        "JEEP", "WRANGLER", "CHEROKEE", "COMPASS", "RENEGADE", "GLADIATOR",
        "COMMANDER", "GRAND CHEROKEE",
    ),
    "Tesla": ("TESLA",),
    "Ford": ("FORD", "MUSTANG", "EXPLORER", "TAURUS", "BRONCO", "KUGA"),
    "Lincoln": ("LINCOLN", "AVIATOR", "NAUTILUS", "CORSAIR"),
    "Toyota": (
        "TOYOTA", "CAMRY", "COROLLA", "PRIUS", "SIENNA", "AVALON", "HIGHLANDER",
    ),
    "Lexus": ("LEXUS",),
    "Honda": ("HONDA", "ACCORD", "CIVIC", "ODYSSEY"),
    "Nissan": ("NISSAN", "ALTIMA", "MAXIMA", "ROGUE"),
    "Infiniti": ("INFINITI",),
    "Cadillac": ("CADILLAC", "ESCALADE"),
    "GMC": ("GMC",),
    "Chrysler": ("CHRYSLER",),
    "Dodge": ("DODGE",),
    "Peugeot": ("PEUGEOT",),
    "Citroen": ("CITROEN", "CITROËN"),
    "Fiat": ("FIAT",),
    "Alfa Romeo": ("ALFA ROMEO", "GIULIA", "STELVIO", "GIULIETTA"),
    "Maserati": ("MASERATI", "GHIBLI", "LEVANTE", "QUATTROPORTE"),
    "Lamborghini": ("LAMBORGHINI", "URUS", "HURACAN", "AVENTADOR"),
    "Ferrari": ("FERRARI",),
    "Bentley": ("BENTLEY",),
    "Rolls-Royce": ("ROLLS-ROYCE", "ROLLS ROYCE"),
    "Subaru": ("SUBARU", "FORESTER", "OUTBACK", "IMPREZA", "LEGACY"),
    "Mitsubishi": ("MITSUBISHI", "OUTLANDER", "PAJERO"),
    "Polestar": ("POLESTAR",),
}


def _compile() -> tuple[tuple[re.Pattern[str], str], ...]:
    """Longest keyword first, so "SANTA FE" wins over "SANTA".

    Boundaries are non-alphanumeric rather than \\b: "K5" must not match inside
    "K50", and "I30" must not match inside "I300".
    """
    pairs = [
        (keyword, brand)
        for brand, keywords in RULES.items()
        for keyword in keywords
    ]
    pairs.sort(key=lambda pair: len(pair[0]), reverse=True)
    return tuple(
        (
            re.compile(
                r"(?<![A-Z0-9])" + keyword.replace(" ", r"\s+") + r"(?![A-Z0-9])"
            ),
            brand,
        )
        for keyword, brand in pairs
    )


_PATTERNS = _compile()

#: Value the Lotte model uses when the maker could not be determined. Kept so
#: the field never becomes null for existing clients.
UNKNOWN_BRAND = "UNKNOWN"


def resolve_manufacturer(name: Optional[str]) -> Optional[str]:
    """Return the English manufacturer for a model/name string, or None."""
    if not name or not isinstance(name, str):
        return None
    upper = name.upper()
    for pattern, brand in _PATTERNS:
        if pattern.search(upper):
            return brand
    return None
