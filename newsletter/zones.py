"""Full names of the bidding zones for any public text (feedback #1: always write country names out; multi-zone
countries say which part). Shared by build.py and diagnose.py; the page keeps its own copy (js/features/flags)."""
from __future__ import annotations

ZONE_NAME = {"AL": "Albania", "AT": "Austria", "BA": "Bosnia and Herzegovina", "BE": "Belgium", "BG": "Bulgaria",
             "CH": "Switzerland", "CZ": "Czechia", "DE-LU": "Germany-Luxembourg", "DK1": "West Denmark", "DK2": "East Denmark",
             "EE": "Estonia", "ES": "Spain", "FI": "Finland", "FR": "France", "GB": "Great Britain", "GR": "Greece",
             "HR": "Croatia", "HU": "Hungary", "IE(SEM)": "Ireland (all-island)", "LT": "Lithuania", "LV": "Latvia",
             "ME": "Montenegro", "MK": "North Macedonia", "NL": "the Netherlands", "PL": "Poland", "PT": "Portugal",
             "RO": "Romania", "RS": "Serbia", "SI": "Slovenia", "SK": "Slovakia", "UA-IPS": "Ukraine",
             "NO1": "Norway (Oslo, NO1)", "NO2": "Norway (south-west, NO2)", "NO3": "Norway (central, NO3)",
             "NO4": "Norway (north, NO4)", "NO5": "Norway (west, NO5)", "SE1": "Sweden (SE1)", "SE2": "Sweden (SE2)",
             "SE3": "Sweden (Stockholm, SE3)", "SE4": "Sweden (Malmö, SE4)", "IT-North": "Northern Italy",
             "IT-Centre-North": "Central-Northern Italy", "IT-Centre-South": "Central-Southern Italy", "IT-South": "Southern Italy",
             "IT-Calabria": "Calabria", "IT-Sicily": "Sicily", "IT-Sardinia": "Sardinia"}

# zones whose day-ahead price is not published in EUR and not converted (metrics.hourly_prices drops them)
NON_EUR = {"UA-IPS": "UAH"}
# price labels that are not an auction result
PRICE_LABEL = {"GB": "Market Index"}


def zn(z: str) -> str:
    return ZONE_NAME.get(z, z)
