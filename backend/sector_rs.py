"""
sector_rs.py
------------
Calculates relative strength for each sector vs S&P 500.
Also assigns investment themes to individual tickers —
themes are narrative-level groupings that cross GICS sectors
and are used for signal card badges + score boosting.
"""

import pandas as pd
import numpy as np
from typing import Optional

# ── Sector ETF proxies ────────────────────────────────────────────────────────
SECTOR_ETFS = {
    "Technology":       "XLK",
    "Financials":       "XLF",
    "Healthcare":       "XLV",
    "Energy":           "XLE",
    "Consumer Disc":    "XLY",
    "Consumer Staples": "XLP",
    "Industrials":      "XLI",
    "Materials":        "XLB",
    "Real Estate":      "XLRE",
    "Utilities":        "XLU",
    "Communication":    "XLC",
    "Semiconductors":   "SOXX",
    "Biotech":          "XBI",
    "Small Cap":        "IWM",
    "Gold Miners":      "GDX",
}

# ── Investment theme map ──────────────────────────────────────────────────────
# Themes are narrative-level groupings: defence spending, AI, gold macro etc.
# Each ticker maps to one theme — the most relevant driving thesis.
# These appear as coloured badges on signal cards and boost signal_score.

THEMES = {
    # ── Defence primes ───────────────────────────────────────────────────────
    "LMT":  "Defence",  "NOC":  "Defence",  "GD":   "Defence",
    "RTX":  "Defence",  "BA":   "Defence",  "LHX":  "Defence",
    "HII":  "Defence",  "GE":   "Defence",  "TDG":  "Defence",
    "HEI":  "Defence",  "LDOS": "Defence",  "SAIC": "Defence",
    "CACI": "Defence",  "BAH":  "Defence",  "GEV":  "Defence",
    "MRCY": "Defence",  "VSEC": "Defence",  "HWM":  "Defence",

    # ── Defence tech: drones, autonomy, hypersonics ──────────────────────────
    "KTOS": "DefenceTech", "AVAV": "DefenceTech", "RCAT": "DefenceTech",
    "ACHR": "DefenceTech", "JOBY": "DefenceTech", "ONDS": "DefenceTech",
    "BBAI": "DefenceTech", "PLTR": "DefenceTech", "AXON": "DefenceTech",
    "BWXT": "DefenceTech", "PL":   "DefenceTech", "IRDM": "DefenceTech",

    # ── Space ────────────────────────────────────────────────────────────────
    "RKLB": "Space", "SATS": "Space", "ASTS": "Space",
    "LUNR": "Space", "RDW":  "Space",

    # ── Cybersecurity ────────────────────────────────────────────────────────
    "CRWD": "Cyber", "PANW": "Cyber", "FTNT": "Cyber",
    "NET":  "Cyber", "ZS":   "Cyber", "OKTA": "Cyber",
    "CYBR": "Cyber", "S":    "Cyber", "TENB": "Cyber",
    "RPD":  "Cyber", "QLYS": "Cyber", "HACK": "Cyber",

    # ── Cloud / SaaS ─────────────────────────────────────────────────────────
    "SNOW": "CloudSaaS", "DDOG": "CloudSaaS", "MDB":  "CloudSaaS",
    "WDAY": "CloudSaaS", "TEAM": "CloudSaaS", "HUBS": "CloudSaaS",
    "MNDY": "CloudSaaS", "BILL": "CloudSaaS", "TOST": "CloudSaaS",
    "GTLB": "CloudSaaS", "ESTC": "CloudSaaS", "CFLT": "CloudSaaS",
    "VEEV": "CloudSaaS", "PCTY": "CloudSaaS", "MANH": "CloudSaaS",
    "APPF": "CloudSaaS", "SPSC": "CloudSaaS", "BRZE": "CloudSaaS",
    "TWLO": "CloudSaaS", "ZI":   "CloudSaaS", "BOX":  "CloudSaaS",
    "DOCU": "CloudSaaS", "RNG":  "CloudSaaS", "FIVN": "CloudSaaS",
    "GWRE": "CloudSaaS", "AZPN": "CloudSaaS", "ALTR": "CloudSaaS",
    "SHOP": "CloudSaaS", "TTD":  "CloudSaaS", "CDNS": "CloudSaaS",
    "ADSK": "CloudSaaS", "SNPS": "CloudSaaS", "INTU": "CloudSaaS",
    "PAYC": "CloudSaaS", "CDAY": "CloudSaaS",

    # ── Gold & precious metals ───────────────────────────────────────────────
    "GLD":  "Gold",  "GDX":  "Gold",  "GDXJ": "Gold",
    "SLV":  "Gold",  "NEM":  "Gold",  "AEM":  "Gold",
    "GOLD": "Gold",  "WPM":  "Gold",  "FNV":  "Gold",
    "RGLD": "Gold",  "AGI":  "Gold",  "KGC":  "Gold",

    # ── Energy: oil & gas ────────────────────────────────────────────────────
    "XOM":  "Energy", "CVX":  "Energy", "COP":  "Energy",
    "EOG":  "Energy", "PXD":  "Energy", "MPC":  "Energy",
    "VLO":  "Energy", "PSX":  "Energy", "DVN":  "Energy",
    "HAL":  "Energy", "SLB":  "Energy", "BKR":  "Energy",
    "OXY":  "Energy", "APA":  "Energy", "MRO":  "Energy",
    "USO":  "Energy", "XLE":  "Energy", "TRGP": "Energy",
    "FANG": "Energy",

    # ── Nuclear & power infra ────────────────────────────────────────────────
    "CEG":  "Nuclear", "VST":  "Nuclear", "NRG":  "Nuclear",
    "CCJ":  "Nuclear", "SMR":  "Nuclear", "OKLO": "Nuclear",
    "GEV":  "Nuclear", "ETN":  "Nuclear",

    # ── Clean energy / renewables ────────────────────────────────────────────
    "ENPH": "CleanEnergy", "FSLR": "CleanEnergy", "NEE":  "CleanEnergy",
    "BE":   "CleanEnergy", "PLUG": "CleanEnergy", "MAXN": "CleanEnergy",
    "STEM": "CleanEnergy", "EVGO": "CleanEnergy", "CHPT": "CleanEnergy",
    "BLNK": "CleanEnergy", "RUN":  "CleanEnergy", "SPWR": "CleanEnergy",

    # ── AI & data infra ──────────────────────────────────────────────────────
    "NVDA": "AI", "AMD":  "AI", "ARM":  "AI",
    "SMCI": "AI", "DELL": "AI", "ORCL": "AI",
    "NOW":  "AI", "CRM":  "AI", "SOUN": "AI",
    "AI":   "AI", "RXRX": "AI", "IONQ": "AI",
    "QUBT": "AI", "RGTI": "AI", "NBIS": "AI",

    # ── Semis ────────────────────────────────────────────────────────────────
    "AVGO": "Semis", "QCOM": "Semis", "AMAT": "Semis",
    "LRCX": "Semis", "KLAC": "Semis", "MRVL": "Semis",
    "MPWR": "Semis", "TXN":  "Semis", "MU":   "Semis",
    "ASML": "Semis", "ON":   "Semis", "MCHP": "Semis",
    "SWKS": "Semis", "QRVO": "Semis", "NXPI": "Semis",
    "ADI":  "Semis", "INTC": "Semis", "SNDK": "Semis",
    "COHR": "Semis", "LITE": "Semis", "CIEN": "Semis",
    "VIAV": "Semis", "TTMI": "Semis", "ACLS": "Semis",
    "KLIC": "Semis", "DIOD": "Semis", "COHU": "Semis",
    "RMBS": "Semis", "SYNA": "Semis", "SLAB": "Semis",

    # ── Data centre infra ────────────────────────────────────────────────────
    "EQIX": "DataCenter", "DLR": "DataCenter", "AMT": "DataCenter",
    "CCI":  "DataCenter", "SBAC":"DataCenter", "IRM": "DataCenter",
    "VRT":  "DataCenter",

    # ── Mega-cap tech ────────────────────────────────────────────────────────
    "AAPL": "MegaTech", "MSFT": "MegaTech", "META": "MegaTech",
    "GOOGL":"MegaTech", "AMZN": "MegaTech", "NFLX": "MegaTech",
    "UBER": "MegaTech",

    # ── Crypto ───────────────────────────────────────────────────────────────
    "COIN": "Crypto", "MSTR": "Crypto", "RIOT": "Crypto",
    "MARA": "Crypto", "CLSK": "Crypto", "WULF": "Crypto",
    "IREN": "Crypto", "CORZ": "Crypto", "HUT":  "Crypto",
    "BTBT": "Crypto", "CIFR": "Crypto",

    # ── Fintech ──────────────────────────────────────────────────────────────
    "HOOD": "Fintech", "AFRM": "Fintech", "UPST": "Fintech",
    "SOFI": "Fintech", "FICO": "Fintech", "V":    "Fintech",
    "MA":   "Fintech", "PYPL": "Fintech", "NDAQ": "Fintech",
    "ICE":  "Fintech", "CME":  "Fintech", "MKTX": "Fintech",
    "GPN":  "Fintech", "FIS":  "Fintech", "RELY": "Fintech",
    "STNE": "Fintech", "PAYO": "Fintech", "LC":   "Fintech",

    # ── EV / next-gen transport ──────────────────────────────────────────────
    "TSLA": "EV", "RIVN": "EV", "LCID": "EV",
    "NIO":  "EV", "XPEV": "EV", "LI":   "EV",
    "LYFT": "EV", "DASH": "EV", "ABNB": "EV",

    # ── MedTech / devices ────────────────────────────────────────────────────
    "ISRG": "MedTech", "BSX":  "MedTech", "EW":   "MedTech",
    "SYK":  "MedTech", "MDT":  "MedTech", "PODD": "MedTech",
    "DXCM": "MedTech", "IDXX": "MedTech", "HOLX": "MedTech",
    "TFX":  "MedTech", "NTRA": "MedTech", "EXAS": "MedTech",
    "GKOS": "MedTech", "INSP": "MedTech", "IRTC": "MedTech",
    "TMDX": "MedTech", "ATRC": "MedTech",

    # ── Biotech / pharma ─────────────────────────────────────────────────────
    "LLY":  "Biotech", "NVO":  "Biotech", "VRTX": "Biotech",
    "REGN": "Biotech", "ALNY": "Biotech", "MRNA": "Biotech",
    "BNTX": "Biotech", "AMGN": "Biotech", "GILD": "Biotech",
    "BIIB": "Biotech", "INCY": "Biotech", "ARWR": "Biotech",
    "CRSP": "Biotech", "BEAM": "Biotech", "EDIT": "Biotech",
    "NTLA": "Biotech", "NUVL": "Biotech", "RXRX": "Biotech",
    "PTGX": "Biotech", "HALO": "Biotech", "MDGL": "Biotech",
    "VKTX": "Biotech", "RYTM": "Biotech", "IMVT": "Biotech",
    "LBPH": "Biotech", "ITCI": "Biotech", "ACAD": "Biotech",
    "AXSM": "Biotech", "BHVN": "Biotech", "PRAX": "Biotech",

    # ── Homebuilders & construction ──────────────────────────────────────────
    "DHI":  "Homebuilders", "LEN":  "Homebuilders", "PHM":  "Homebuilders",
    "NVR":  "Homebuilders", "TOL":  "Homebuilders", "MTH":  "Homebuilders",
    "BLDR": "Homebuilders", "MHO":  "Homebuilders", "IBP":  "Homebuilders",
    "ITB":  "Homebuilders", "TREX": "Homebuilders",

    # ── Restaurants / consumer brands ────────────────────────────────────────
    "CMG":  "Restaurants", "MCD":  "Restaurants", "SBUX": "Restaurants",
    "CAVA": "Restaurants", "SHAK": "Restaurants", "TXRH": "Restaurants",
    "WING": "Restaurants", "DPZ":  "Restaurants", "YUM":  "Restaurants",
    "QSR":  "Restaurants", "JACK": "Restaurants", "BROS": "Restaurants",
    "PTLO": "Restaurants", "DNUT": "Restaurants", "NDLS": "Restaurants",

    # ── Consumer growth ──────────────────────────────────────────────────────
    "CELH": "ConsumerGrowth", "DUOL": "ConsumerGrowth", "ONON": "ConsumerGrowth",
    "DECK": "ConsumerGrowth", "ELF":  "ConsumerGrowth", "HIMS": "ConsumerGrowth",
    "DKNG": "ConsumerGrowth", "RDDT": "ConsumerGrowth", "RBLX": "ConsumerGrowth",
    "PINS": "ConsumerGrowth", "SNAP": "ConsumerGrowth", "SPOT": "ConsumerGrowth",
    "ROKU": "ConsumerGrowth", "TTWO": "ConsumerGrowth", "EA":   "ConsumerGrowth",
    "OLPX": "ConsumerGrowth", "XPOF": "ConsumerGrowth", "FIGS": "ConsumerGrowth",
    "LULU": "ConsumerGrowth", "NKE":  "ConsumerGrowth", "SKX":  "ConsumerGrowth",
    "CROX": "ConsumerGrowth", "BOOT": "ConsumerGrowth",

    # ── Industrials / infrastructure ─────────────────────────────────────────
    "CAT":  "Industrials", "DE":   "Industrials", "EMR":  "Industrials",
    "HON":  "Industrials", "PH":   "Industrials", "ROK":  "Industrials",
    "AME":  "Industrials", "FAST": "Industrials", "PWR":  "Industrials",
    "URI":  "Industrials", "WAB":  "Industrials", "GNRC": "Industrials",
    "CARR": "Industrials", "OTIS": "Industrials", "ITW":  "Industrials",
    "IR":   "Industrials", "TT":   "Industrials", "XYL":  "Industrials",
    "HUBB": "Industrials", "TRMB": "Industrials", "AAON": "Industrials",

    # ── Logistics / freight ──────────────────────────────────────────────────
    "FDX":  "Logistics", "UPS":  "Logistics", "ODFL": "Logistics",
    "JBHT": "Logistics", "CHRW": "Logistics", "ARCB": "Logistics",
    "NSC":  "Logistics", "UNP":  "Logistics", "CSX":  "Logistics",
    "CPRT": "Logistics", "EXPD": "Logistics",
}

# ── Theme metadata ────────────────────────────────────────────────────────────
# label: display string on the badge
# color: badge background colour
# score_bonus: added to signal_score (max 10)
# priority: True = always apply bonus; False = only when sector is leading/improving
THEME_META = {
    "Defence":       {"label": "🛡 Defence",      "color": "#1c3d5a", "score_bonus": 0.6, "priority": True},
    "DefenceTech":   {"label": "🚁 Def-Tech",     "color": "#1a3a52", "score_bonus": 0.8, "priority": True},
    "Space":         {"label": "🚀 Space",         "color": "#2d1b6e", "score_bonus": 0.7, "priority": True},
    "Cyber":         {"label": "🔐 Cyber",         "color": "#0a1a3d", "score_bonus": 0.5, "priority": False},
    "CloudSaaS":     {"label": "☁ Cloud",          "color": "#0a2040", "score_bonus": 0.4, "priority": False},
    "Gold":          {"label": "🥇 Gold",          "color": "#5a3e00", "score_bonus": 0.6, "priority": True},
    "Energy":        {"label": "⛽ Energy",        "color": "#4a2000", "score_bonus": 0.4, "priority": False},
    "Nuclear":       {"label": "⚡ Nuclear",       "color": "#1a3a1a", "score_bonus": 0.5, "priority": False},
    "CleanEnergy":   {"label": "🌱 Clean",         "color": "#0a3a1a", "score_bonus": 0.3, "priority": False},
    "AI":            {"label": "🤖 AI",            "color": "#0d3d26", "score_bonus": 0.5, "priority": False},
    "Semis":         {"label": "💾 Semis",         "color": "#0a2d4a", "score_bonus": 0.4, "priority": False},
    "DataCenter":    {"label": "🏢 DataCtr",       "color": "#1a1a3d", "score_bonus": 0.4, "priority": False},
    "MegaTech":      {"label": "📱 Mega-Tech",     "color": "#0a2235", "score_bonus": 0.3, "priority": False},
    "Crypto":        {"label": "₿ Crypto",         "color": "#3d1e00", "score_bonus": 0.3, "priority": False},
    "Fintech":       {"label": "💳 Fintech",       "color": "#0a2d1a", "score_bonus": 0.3, "priority": False},
    "EV":            {"label": "🔋 EV",            "color": "#1a3d1a", "score_bonus": 0.3, "priority": False},
    "MedTech":       {"label": "🏥 MedTech",       "color": "#0a2d2d", "score_bonus": 0.4, "priority": False},
    "Biotech":       {"label": "🧬 Biotech",       "color": "#0a2d0a", "score_bonus": 0.4, "priority": False},
    "Homebuilders":  {"label": "🏠 Builders",      "color": "#3d2d0a", "score_bonus": 0.3, "priority": False},
    "Restaurants":   {"label": "🍔 Restaurants",   "color": "#3d1a0a", "score_bonus": 0.3, "priority": False},
    "ConsumerGrowth":{"label": "🛍 Consumer",      "color": "#2d1a0a", "score_bonus": 0.3, "priority": False},
    "Industrials":   {"label": "⚙ Industrial",    "color": "#2d2d0a", "score_bonus": 0.3, "priority": False},
    "Logistics":     {"label": "🚚 Logistics",     "color": "#1a2d0a", "score_bonus": 0.3, "priority": False},
    # ── GICS sector fallbacks ─────────────────────────────────────────────────
    "Technology":    {"label": "💻 Tech",           "color": "#0a1a2d", "score_bonus": 0.2, "priority": False},
    "Media":         {"label": "📡 Media",          "color": "#1a0a2d", "score_bonus": 0.2, "priority": False},
    "ConsumerDisc":  {"label": "🛒 Cons.Disc",      "color": "#2d1a00", "score_bonus": 0.2, "priority": False},
    "Staples":       {"label": "🧴 Staples",        "color": "#1a2d1a", "score_bonus": 0.1, "priority": False},
    "Healthcare":    {"label": "🏥 Healthcare",     "color": "#0a2d2d", "score_bonus": 0.2, "priority": False},
    "Financials":    {"label": "🏦 Financials",     "color": "#0a1a0a", "score_bonus": 0.2, "priority": False},
    "Materials":     {"label": "⛏ Materials",      "color": "#2d2000", "score_bonus": 0.2, "priority": False},
    "REITs":         {"label": "🏢 REITs",          "color": "#1a1a0a", "score_bonus": 0.1, "priority": False},
    "Utilities":     {"label": "💡 Utilities",      "color": "#0a2a1a", "score_bonus": 0.1, "priority": False},
    "ETF":           {"label": "📊 ETF",            "color": "#1a1a1a", "score_bonus": 0.0, "priority": False},
    "SmallCap":      {"label": "🔬 Small Cap",      "color": "#1a0a2a", "score_bonus": 0.2, "priority": False},
    "ShortWatch":    {"label": "📉 Short",          "color": "#3d0a0a", "score_bonus": 0.0, "priority": False},
}

# ── GICS sector map ───────────────────────────────────────────────────────────
STOCK_SECTOR_MAP = {
    "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Semiconductors",
    "AMD": "Semiconductors", "AVGO": "Semiconductors", "QCOM": "Semiconductors",
    "AMAT": "Semiconductors", "LRCX": "Semiconductors", "KLAC": "Semiconductors",
    "MRVL": "Semiconductors", "ARM": "Semiconductors", "SMCI": "Technology",
    "ORCL": "Technology", "CRM": "Technology", "ADBE": "Technology",
    "NOW": "Technology", "PLTR": "Technology", "APP": "Technology",
    "PANW": "Technology", "CRWD": "Technology", "FTNT": "Technology",
    "NET": "Technology", "DDOG": "Technology", "SNOW": "Technology",
    "COIN": "Financials", "HOOD": "Financials", "FICO": "Financials",
    "V": "Financials", "MA": "Financials", "GS": "Financials",
    "JPM": "Financials", "MS": "Financials",
    "TSLA": "Consumer Disc", "DECK": "Consumer Disc", "ONON": "Consumer Disc",
    "CELH": "Consumer Disc", "ELF": "Consumer Disc", "CAVA": "Consumer Disc",
    "AMZN": "Consumer Disc", "UBER": "Consumer Disc", "LYFT": "Consumer Disc",
    "ABNB": "Consumer Disc", "DASH": "Consumer Disc",
    "DUOL": "Communication", "RBLX": "Communication", "SNAP": "Communication",
    "PINS": "Communication", "SPOT": "Communication", "META": "Communication",
    "GOOGL": "Communication", "NFLX": "Communication",
    "RXRX": "Biotech", "ALNY": "Biotech", "ARWR": "Biotech",
    "MRNA": "Healthcare", "BNTX": "Healthcare",
    "LLY": "Healthcare", "ISRG": "Healthcare", "VRTX": "Healthcare",
    "LMT": "Industrials", "NOC": "Industrials", "GD": "Industrials",
    "RTX": "Industrials", "BA": "Industrials", "LHX": "Industrials",
    "KTOS": "Industrials", "AVAV": "Industrials", "AXON": "Technology",
    "RKLB": "Industrials", "SATS": "Communication", "ASTS": "Communication",
    "LUNR": "Industrials",
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy", "EOG": "Energy",
    "HAL": "Energy", "SLB": "Energy", "OXY": "Energy",
    "GLD": "Materials", "GDX": "Gold Miners", "GDXJ": "Gold Miners",
    "SLV": "Materials", "NEM": "Gold Miners",
    # ── Additional S&P 500 & universe coverage ────────────────────────────────
    "A":"Industrials", "AAL":"Industrials", "ABBV":"Healthcare", "ABT":"Healthcare",
    "ACGL":"Financials", "ACN":"Technology", "ADM":"Consumer Staples", "AEE":"Utilities",
    "AEP":"Utilities", "AES":"Utilities", "AFL":"Financials", "AIG":"Financials",
    "AIZ":"Financials", "AJG":"Financials", "AKAM":"Technology", "ALB":"Materials",
    "ALL":"Financials", "ALLE":"Industrials", "AMCR":"Materials", "AMP":"Financials",
    "ANET":"Technology", "AON":"Financials", "AOS":"Industrials", "APD":"Materials",
    "APH":"Technology", "APTV":"Consumer Disc", "ARE":"Real Estate", "ATO":"Utilities",
    "AVB":"Real Estate", "AVY":"Materials", "AWK":"Utilities", "AXP":"Financials",
    "AZO":"Consumer Disc", "BAC":"Financials", "BALL":"Materials", "BAX":"Healthcare",
    "BBWI":"Consumer Disc", "BBY":"Consumer Disc", "BDX":"Healthcare", "BEN":"Financials",
    "BF-B":"Consumer Staples", "BIO":"Healthcare", "BK":"Financials", "BKNG":"Consumer Disc",
    "BLK":"Financials", "BMY":"Healthcare", "BR":"Technology", "BRK-B":"Financials",
    "BRO":"Financials", "BX":"Financials", "C":"Financials", "CAG":"Consumer Staples",
    "CAH":"Healthcare", "CB":"Financials", "CBOE":"Financials", "CBRE":"Real Estate",
    "CCL":"Consumer Disc", "CDW":"Technology", "CE":"Materials", "CF":"Materials",
    "CFG":"Financials", "CHD":"Consumer Staples", "CHTR":"Communication", "CI":"Healthcare",
    "CINF":"Financials", "CL":"Consumer Staples", "CLX":"Consumer Staples", "CMI":"Industrials",
    "CMS":"Utilities", "CNC":"Healthcare", "CNP":"Utilities", "COF":"Financials",
    "COO":"Healthcare", "COR":"Healthcare", "COST":"Consumer Disc", "CPAY":"Financials",
    "CPB":"Consumer Staples", "CPT":"Real Estate", "CSGP":"Real Estate", "CTAS":"Industrials",
    "CTRA":"Energy", "CTSH":"Technology", "CTVA":"Materials", "CVS":"Healthcare",
    "CZR":"Consumer Disc", "D":"Utilities", "DAL":"Industrials", "DAY":"Industrials",
    "DD":"Materials", "DG":"Consumer Disc", "DGX":"Healthcare", "DHR":"Healthcare",
    "DLTR":"Consumer Disc", "DOC":"Real Estate", "DOV":"Industrials", "DOW":"Materials",
    "DRI":"Consumer Disc", "DTE":"Utilities", "DUK":"Utilities", "DVA":"Healthcare",
    "EBAY":"Consumer Disc", "ECL":"Materials", "ED":"Utilities", "EFX":"Financials",
    "EG":"Financials", "EIX":"Utilities", "EL":"Consumer Disc", "ELV":"Healthcare",
    "EMN":"Materials", "EPAM":"Technology", "EQR":"Real Estate", "EQT":"Energy",
    "ES":"Utilities", "ESS":"Real Estate", "ETR":"Utilities", "ETSY":"Consumer Disc",
    "EVRG":"Utilities", "EXC":"Utilities", "EXPE":"Consumer Disc", "EXR":"Real Estate",
    "F":"Consumer Disc", "FCX":"Materials", "FDS":"Financials", "FE":"Utilities",
    "FFIV":"Technology", "FI":"Financials", "FITB":"Financials", "FLT":"Financials",
    "FMC":"Materials", "FOXA":"Communication", "FRT":"Real Estate", "FTV":"Industrials",
    "GDDY":"Technology", "GEHC":"Healthcare", "GEN":"Technology", "GIS":"Consumer Staples",
    "GL":"Financials", "GLW":"Technology", "GM":"Consumer Disc", "GOOG":"Communication",
    "GPC":"Consumer Disc", "GRMN":"Technology", "GWW":"Industrials", "HAS":"Consumer Disc",
    "HBAN":"Financials", "HCA":"Healthcare", "HD":"Consumer Disc", "HIG":"Financials",
    "HLT":"Consumer Disc", "HRL":"Consumer Staples", "HSIC":"Healthcare", "HST":"Real Estate",
    "HSY":"Consumer Staples", "HUM":"Healthcare", "IEX":"Industrials", "IFF":"Materials",
    "INVH":"Real Estate", "IP":"Materials", "IPG":"Communication", "IQV":"Healthcare",
    "IT":"Industrials", "IVZ":"Financials", "J":"Industrials", "JBL":"Technology",
    "JCI":"Industrials", "JKHY":"Technology", "JNJ":"Healthcare", "K":"Consumer Staples",
    "KDP":"Consumer Staples", "KEY":"Financials", "KEYS":"Technology", "KHC":"Consumer Staples",
    "KIM":"Real Estate", "KMB":"Consumer Staples", "KMI":"Energy", "KMX":"Consumer Disc",
    "KO":"Consumer Staples", "KR":"Consumer Staples", "KVUE":"Consumer Staples",
    "L":"Financials", "LH":"Healthcare", "LIN":"Materials", "LKQ":"Consumer Disc",
    "LNT":"Utilities", "LOW":"Consumer Disc", "LUV":"Industrials", "LVS":"Consumer Disc",
    "LW":"Consumer Staples", "LYB":"Materials", "LYV":"Communication", "MAA":"Real Estate",
    "MAR":"Consumer Disc", "MAS":"Industrials", "MCK":"Healthcare", "MCO":"Financials",
    "MDLZ":"Consumer Staples", "MET":"Financials", "MGM":"Consumer Disc", "MHK":"Consumer Disc",
    "MKC":"Consumer Staples", "MLM":"Materials", "MMC":"Financials", "MMM":"Industrials",
    "MNST":"Consumer Staples", "MO":"Consumer Staples", "MOH":"Healthcare", "MOS":"Materials",
    "MSCI":"Financials", "MSI":"Technology", "MTB":"Financials", "MTCH":"Communication",
    "MTD":"Healthcare", "NCLH":"Consumer Disc", "NDSN":"Industrials", "NI":"Utilities",
    "NTAP":"Technology", "NTRS":"Financials", "NUE":"Materials", "NWL":"Consumer Disc",
    "NWS":"Communication", "O":"Real Estate", "OKE":"Energy", "OMC":"Communication",
    "ORLY":"Consumer Disc", "PAYX":"Technology", "PCAR":"Industrials", "PCG":"Utilities",
    "PEG":"Utilities", "PEP":"Consumer Staples", "PFE":"Healthcare", "PFG":"Financials",
    "PG":"Consumer Staples", "PGR":"Financials", "PKG":"Materials", "PM":"Consumer Staples",
    "PNC":"Financials", "PNR":"Industrials", "PNW":"Utilities", "POOL":"Consumer Disc",
    "PPG":"Materials", "PPL":"Utilities", "PRU":"Financials", "PSA":"Real Estate",
    "PTC":"Technology", "RCL":"Consumer Disc", "REG":"Real Estate", "RF":"Financials",
    "RJF":"Financials", "RMD":"Healthcare", "ROL":"Industrials", "ROP":"Industrials",
    "ROST":"Consumer Disc", "RSG":"Industrials", "RVTY":"Healthcare", "SEE":"Materials",
    "SHW":"Materials", "SJM":"Consumer Staples", "SNA":"Industrials", "SO":"Utilities",
    "SOLV":"Healthcare", "SPG":"Real Estate", "SPGI":"Financials", "SRE":"Utilities",
    "STLD":"Materials", "STT":"Financials", "STZ":"Consumer Staples", "SWK":"Industrials",
    "SYF":"Financials", "SYY":"Consumer Staples", "T":"Communication", "TAP":"Consumer Staples",
    "TDY":"Industrials", "TECH":"Healthcare", "TEL":"Technology", "TER":"Semiconductors",
    "TFC":"Financials", "TGT":"Consumer Disc", "TJX":"Consumer Disc", "TMO":"Healthcare",
    "TMUS":"Communication", "TPR":"Consumer Disc", "TROW":"Financials", "TRV":"Financials",
    "TSCO":"Consumer Disc", "TSN":"Consumer Staples", "TXT":"Industrials", "TYL":"Technology",
    "UAL":"Industrials", "UDR":"Real Estate", "UHS":"Healthcare", "ULTA":"Consumer Disc",
    "UNH":"Healthcare", "USB":"Financials", "VICI":"Real Estate", "VLTO":"Industrials",
    "VRSK":"Industrials", "VRSN":"Technology", "VTR":"Real Estate", "VTRS":"Healthcare",
    "VZ":"Communication", "WAT":"Healthcare", "WBA":"Consumer Staples", "WEC":"Utilities",
    "WELL":"Real Estate", "WFC":"Financials", "WHR":"Consumer Disc", "WM":"Industrials",
    "WMB":"Energy", "WMT":"Consumer Disc", "WST":"Healthcare", "WTW":"Financials",
    "WY":"Real Estate", "WYNN":"Consumer Disc", "XEL":"Utilities", "ZBH":"Healthcare",
    "ZBRA":"Technology", "ZTS":"Healthcare",
}


def get_sector(ticker: str) -> str:
    return STOCK_SECTOR_MAP.get(ticker, "Technology")


# GICS sector → theme fallback
_SECTOR_FALLBACK = {
    "Technology":      "Technology",
    "Semiconductors":  "Semis",
    "Communication":   "Media",
    "Consumer Disc":   "ConsumerDisc",
    "Consumer Staples":"Staples",
    "Healthcare":      "Healthcare",
    "Financials":      "Financials",
    "Industrials":     "Industrials",
    "Energy":          "Energy",
    "Materials":       "Materials",
    "Real Estate":     "REITs",
    "Utilities":       "Utilities",
    "Gold Miners":     "Gold",
    "Biotech":         "Biotech",
}

def _build_watchlist_fallback() -> dict:
    """Build ticker→theme map from watchlist group membership."""
    try:
        import watchlist as _wl
        mapping = {}
        # ETFs
        for t in getattr(_wl, "ETFS", []):
            if t not in mapping: mapping[t] = "ETF"
        # Crypto ecosystem
        for t in getattr(_wl, "CRYPTO", []):
            if t not in mapping: mapping[t] = "Crypto"
        # Biotech
        for t in getattr(_wl, "BIOTECH", []):
            if t not in mapping: mapping[t] = "Biotech"
        # Large cap tech / growth SaaS
        for t in getattr(_wl, "LARGE_CAP_TECH", []):
            if t not in mapping: mapping[t] = "CloudSaaS"
        # Momentum names — tag by GICS if known, else ConsumerGrowth
        for t in getattr(_wl, "MOMENTUM", []):
            if t not in mapping: mapping[t] = "ConsumerGrowth"
        # Short watch — tag but no bonus
        for t in getattr(_wl, "SHORT_WATCH", []):
            if t not in mapping: mapping[t] = "ShortWatch"
        # S&P 500 — use GICS sector
        for t in getattr(_wl, "SP500", []):
            if t not in mapping:
                sector = STOCK_SECTOR_MAP.get(t)
                if sector:
                    mapping[t] = _SECTOR_FALLBACK.get(sector, sector)
        # Russell 2000
        for t in getattr(_wl, "RUSSELL2000", []):
            if t not in mapping:
                sector = STOCK_SECTOR_MAP.get(t)
                if sector:
                    mapping[t] = _SECTOR_FALLBACK.get(sector, sector)
                else:
                    mapping[t] = "SmallCap"
        return mapping
    except Exception:
        return {}

_WATCHLIST_FALLBACK: dict = {}

def get_theme(ticker: str) -> Optional[str]:
    """Return the investment theme for a ticker.
    Priority: curated THEMES → watchlist group → GICS sector fallback.
    """
    global _WATCHLIST_FALLBACK
    if ticker in THEMES:
        return THEMES[ticker]
    # Build watchlist fallback on first call
    if not _WATCHLIST_FALLBACK:
        _WATCHLIST_FALLBACK = _build_watchlist_fallback()
    if ticker in _WATCHLIST_FALLBACK:
        return _WATCHLIST_FALLBACK[ticker]
    # Final fallback: GICS sector
    sector = STOCK_SECTOR_MAP.get(ticker)
    if sector:
        return _SECTOR_FALLBACK.get(sector, sector)
    return None


def get_theme_meta(theme: str) -> dict:
    """Return display metadata for a theme."""
    return THEME_META.get(theme, {})


def get_theme_score_bonus(theme: str, sector_rs_data: dict = None) -> float:
    """
    Score bonus for a themed ticker.
    Priority themes always get their bonus.
    Non-priority themes only get it if their sector is leading/improving.
    """
    if not theme:
        return 0.0
    meta = THEME_META.get(theme, {})
    bonus = meta.get("score_bonus", 0.0)
    if meta.get("priority", False):
        return bonus
    if sector_rs_data:
        # find the sector this theme's tickers generally fall in
        # rough heuristic: use the first ticker in THEMES with this theme
        representative = next(
            (t for t, th in THEMES.items() if th == theme),
            None
        )
        sector = STOCK_SECTOR_MAP.get(representative or "", "Technology")
        s_data = sector_rs_data.get(sector, {})
        if s_data.get("trend") in ("leading", "improving"):
            return bonus
        return 0.0
    return bonus * 0.5


def calculate_sector_rs(bars_data: dict, benchmark: str = "SPY") -> dict:
    if benchmark not in bars_data:
        return {}

    spy_closes = bars_data[benchmark]["close"]
    spy_ret_1d = _period_return(spy_closes, 1)
    spy_ret_1w = _period_return(spy_closes, 5)
    spy_ret_1m = _period_return(spy_closes, 21)
    spy_ret_3m = _period_return(spy_closes, 63)

    sector_results = {}

    for sector_name, etf in SECTOR_ETFS.items():
        if etf not in bars_data:
            continue

        closes = bars_data[etf]["close"]
        price = float(closes.iloc[-1])
        ret_1d = _period_return(closes, 1)
        ret_1w = _period_return(closes, 5)
        ret_1m = _period_return(closes, 21)
        ret_3m = _period_return(closes, 63)

        rs_1d = round((ret_1d - spy_ret_1d) * 100, 2) if ret_1d and spy_ret_1d else 0
        rs_1w = round((ret_1w - spy_ret_1w) * 100, 2) if ret_1w and spy_ret_1w else 0
        rs_1m = round((ret_1m - spy_ret_1m) * 100, 2) if ret_1m and spy_ret_1m else 0
        rs_3m = round((ret_3m - spy_ret_3m) * 100, 2) if ret_3m and spy_ret_3m else 0

        ma21 = float(closes.iloc[-21:].mean()) if len(closes) >= 21 else None
        above_ma21 = bool(ma21 and price > ma21)

        if rs_1m > 2 and rs_3m > 2:
            trend = "leading"
        elif rs_1m < -2 and rs_3m < -2:
            trend = "lagging"
        elif rs_1m > 0:
            trend = "improving"
        else:
            trend = "neutral"

        sector_results[sector_name] = {
            "etf": etf,
            "price": round(price, 2),
            "chg_1d": round(ret_1d * 100, 2) if ret_1d else 0,
            "ret_1w_pct": round(ret_1w * 100, 2) if ret_1w else 0,
            "ret_1m_pct": round(ret_1m * 100, 2) if ret_1m else 0,
            "ret_3m_pct": round(ret_3m * 100, 2) if ret_3m else 0,
            "rs_vs_spy_1d": rs_1d,
            "rs_vs_spy_1w": rs_1w,
            "rs_vs_spy_1m": rs_1m,
            "rs_vs_spy_3m": rs_3m,
            "above_ma21": above_ma21,
            "trend": trend,
        }

    sorted_sectors = sorted(
        sector_results.items(),
        key=lambda x: x[1]["rs_vs_spy_1m"],
        reverse=True
    )
    for rank, (name, _) in enumerate(sorted_sectors, 1):
        sector_results[name]["rank"] = rank
        sector_results[name]["rank_of"] = len(sorted_sectors)

    return sector_results


def _period_return(closes: pd.Series, periods: int) -> Optional[float]:
    if len(closes) < periods + 1:
        return None
    start = float(closes.iloc[-(periods + 1)])
    end = float(closes.iloc[-1])
    if start == 0:
        return None
    return (end - start) / start


def enrich_with_sector(stock: dict) -> dict:
    """Add sector and theme to a stock dict."""
    ticker = stock.get("ticker", "")
    stock["sector"] = get_sector(ticker)
    stock["theme"]  = get_theme(ticker)
    return stock


# ── Sector rotation signal ────────────────────────────────────────────────────

def get_sector_rotation_bias(sector_data: dict) -> dict:
    """
    Derives a sector rotation bias signal from current RS rankings.
    Used to bias individual stock signals toward leading sectors.

    Logic:
    - Top 3 sectors by 1-month RS that are also above their MA21 → LEADING
    - Bottom 3 sectors by 1-month RS → LAGGING
    - Sector score bonus: +0.5 signal score for stocks in leading sectors
    - Sector score penalty: stocks in lagging sectors require higher base score

    Returns:
      leading: list of top sector names currently leading the market
      lagging: list of bottom sector names lagging
      bias_map: {sector_name: float} — bias score for each sector
      rotation_alert: str if there is a notable rotation happening
    """
    if not sector_data:
        return {"leading": [], "lagging": [], "bias_map": {}, "rotation_alert": None}

    # Sort by 1-month RS vs SPY
    ranked = sorted(
        sector_data.items(),
        key=lambda x: x[1].get("rs_vs_spy_1m", 0),
        reverse=True,
    )

    leading_sectors = []
    lagging_sectors = []
    bias_map: dict  = {}

    for i, (sector_name, data) in enumerate(ranked):
        rs_1m       = data.get("rs_vs_spy_1m", 0)
        rs_3m       = data.get("rs_vs_spy_3m", 0)
        above_ma21  = data.get("above_ma21", False)
        trend       = data.get("trend", "neutral")
        n           = len(ranked)

        # Leading: top 3, positive RS on both timeframes, above MA21
        if i < 3 and rs_1m > 1.5 and above_ma21:
            leading_sectors.append(sector_name)
            bias_map[sector_name] = round(min(rs_1m / 5, 1.0), 2)   # 0-1 bonus

        # Lagging: bottom 3, negative RS on both timeframes
        elif i >= n - 3 and rs_1m < -1.5 and rs_3m < -1.5:
            lagging_sectors.append(sector_name)
            bias_map[sector_name] = round(max(rs_1m / 5, -1.0), 2)  # 0 to -1 penalty

        else:
            bias_map[sector_name] = 0.0

    # Detect notable rotation: sector moved from lagging to leading recently
    # Simple heuristic: top-ranked sector has strong 1m but weak 3m (new rotation)
    rotation_alert = None
    if ranked:
        top_name, top_data = ranked[0]
        if top_data.get("rs_vs_spy_1m", 0) > 3 and top_data.get("rs_vs_spy_3m", 0) < 1:
            rotation_alert = (
                f"⚡ Rotation into {top_name}: strong 1m RS ({top_data['rs_vs_spy_1m']:+.1f}%) "
                f"but weak 3m RS ({top_data['rs_vs_spy_3m']:+.1f}%) — new money flowing in"
            )

    # Build readable summary
    leading_str  = ", ".join(leading_sectors) if leading_sectors else "None"
    lagging_str  = ", ".join(lagging_sectors) if lagging_sectors else "None"

    return {
        "leading":          leading_sectors,
        "lagging":          lagging_sectors,
        "bias_map":         bias_map,
        "rotation_alert":   rotation_alert,
        "summary":          f"Leading: {leading_str} | Lagging: {lagging_str}",
        "ranked_sectors":   [
            {
                "rank":       i + 1,
                "sector":     name,
                "rs_1m":      data.get("rs_vs_spy_1m", 0),
                "rs_3m":      data.get("rs_vs_spy_3m", 0),
                "trend":      data.get("trend"),
                "above_ma21": data.get("above_ma21"),
                "etf":        data.get("etf"),
            }
            for i, (name, data) in enumerate(ranked)
        ],
    }


def apply_sector_bias_to_signals(signals: list, sector_data: dict) -> list:
    """
    Adjusts signal scores based on sector rotation bias.
    Stocks in leading sectors get +0.3 to signal_score.
    Stocks in lagging sectors get -0.3 from signal_score (harder to qualify).
    Called after screener, before alert filtering.
    """
    if not sector_data or not signals:
        return signals

    rotation = get_sector_rotation_bias(sector_data)
    bias_map  = rotation.get("bias_map", {})

    for sig in signals:
        sector = sig.get("sector")
        bias   = bias_map.get(sector, 0.0)
        if bias != 0.0:
            orig_score = sig.get("signal_score", 0) or 0
            sig["signal_score"]    = round(orig_score + bias * 0.5, 2)  # 0-0.5 adjustment
            sig["sector_bias"]     = bias
            sig["sector_rotation"] = "leading" if bias > 0 else "lagging"
        else:
            sig["sector_bias"]     = 0.0
            sig["sector_rotation"] = "neutral"

    return signals
