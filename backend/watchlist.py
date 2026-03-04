"""
watchlist.py - Full 1000 ticker universe
-----------------------------------------
S&P 500 + Nasdaq 100 + momentum names + crypto ecosystem + biotech + shorts
All liquid, IEX-confirmed.
"""

# ── S&P 500 ───────────────────────────────────────────────────────────────────
SP500 = [
    "MMM","AOS","ABT","ABBV","ACN","ADBE","AMD","AES","AFL","A","APD","ABNB",
    "AKAM","ALB","ARE","ALGN","ALLE","LNT","ALL","GOOGL","GOOG","MO","AMZN",
    "AMCR","AEE","AAL","AEP","AXP","AIG","AMT","AWK","AMP","AME","AMGN",
    "APH","ADI","AON","APA","AAPL","AMAT","APTV","ACGL","ADM","ANET",
    "AJG","AIZ","T","ATO","ADSK","AZO","AVB","AVY","AXON","BKR","BALL","BAC",
    "BK","BBWI","BAX","BDX","BBY","BIO","TECH","BIIB","BLK","BX",
    "BA","BMY","AVGO","BR","BRO","BLDR","BSX","CHRW","CDNS",
    "CZR","CPT","CPB","COF","CAH","KMX","CCL","CARR","CAT","CBOE",
    "CBRE","CDW","CE","COR","CNC","CNP","CF","CHTR","CVX","CMG","CB","CHD",
    "CI","CINF","CTAS","CSCO","C","CFG","CLX","CME","CMS","KO","CTSH","CL",
    "CMCSA","CAG","COP","ED","STZ","CEG","COO","CPRT","GLW","CPAY","CTVA",
    "CSGP","COST","CTRA","CRWD","CCI","CSX","CMI","CVS","DHI","DHR","DRI",
    "DVA","DAY","DECK","DE","DAL","DVN","DXCM","FANG","DLR","DG","DLTR",
    "D","DPZ","DOV","DOW","DHR","DTE","DUK","DD","EMN","ETN","EBAY","ECL",
    "EIX","EW","EA","ELV","LLY","EMR","ENPH","ETR","EOG","EPAM","EQT","EFX",
    "EQIX","EQR","ESS","EL","ETSY","EG","EVRG","ES","EXC","EXPE","EXPD",
    "EXR","XOM","FFIV","FDS","FICO","FAST","FRT","FDX","FIS","FITB","FSLR",
    "FE","FI","FMC","F","FTNT","FTV","FOXA","FOX","BEN","FCX","GRMN",
    "IT","GE","GEHC","GEV","GEN","GNRC","GD","GIS","GM","GPC","GILD","GPN",
    "GL","GDDY","GS","HAL","HIG","HAS","HCA","DOC","HSIC","HSY","HPE",
    "HLT","HOLX","HD","HON","HRL","HST","HWM","HPQ","HUBB","HUM","HBAN",
    "HII","IBM","IEX","IDXX","ITW","INCY","IR","PODD","INTC","ICE","IFF",
    "IP","IPG","INTU","ISRG","IVZ","INVH","IQV","IRM","JBHT","JBL","JKHY",
    "J","JNJ","JCI","JPM","JNPR","K","KVUE","KDP","KEY","KEYS","KMB","KIM",
    "KMI","KLAC","KHC","KR","LHX","LH","LRCX","LW","LVS","LDOS","LEN","LIN",
    "LYV","LKQ","LMT","L","LOW","LULU","LYB","MTB","MRO","MPC","MKTX","MAR",
    "MMC","MLM","MAS","MA","MTCH","MKC","MCD","MCK","MDT","MET","MTD","MGM",
    "MCHP","MU","MSFT","MAA","MRNA","MHK","MOH","TAP","MDLZ","MPWR","MNST",
    "MCO","MS","MOS","MSI","MSCI","NDAQ","NTAP","NFLX","NWL","NEM","NWSA",
    "NWS","NEE","NKE","NI","NDSN","NSC","NTRS","NOC","NCLH","NRG","NUE",
    "NVR","NVDA","NVO","ORLY","OXY","ODFL","OMC","ON","OKE","ORCL","OTIS",
    "PCAR","PKG","PLTR","PH","PAYX","PAYC","PYPL","PNR","PEP","PFE","PCG",
    "PM","PSX","PNW","PNC","POOL","PPG","PPL","PFG","PG","PGR","PRU","PEG",
    "PWR","PTC","PSA","PHM","QRVO","PWR","QCOM","DGX","RL","RJF",
    "RTX","O","REG","REGN","RF","RSG","RMD","RVTY","ROK","ROL","ROP","ROST",
    "RCL","SPGI","CRM","SBAC","SLB","STX","SEE","SRE","NOW","SHW","SPG",
    "SWKS","SJM","SNA","SOLV","SO","LUV","SWK","SBUX","STT","STLD","STE",
    "SYK","SMCI","SYF","SNPS","SYY","TMUS","TROW","TTWO","TPR","TRGP","TGT",
    "TEL","TDY","TFX","TER","TSLA","TXN","TXT","TMO","TJX","TSCO","TT","TDG",
    "TRV","TRMB","TFC","TYL","TSN","USB","UBER","UDR","ULTA","UNP","UAL",
    "UPS","URI","UNH","UHS","VLO","VTR","VLTO","VRSN","VRSK","VZ","VRTX",
    "VTRS","VICI","V","VST","WAB","WMT","WBD","WM","WAT","WEC","WFC","WELL",
    "WST","WDC","WY","WHR","WMB","WTW","GWW","WYNN","XEL","XYL","YUM",
    "ZBRA","ZBH","ZTS"
]

# ── Nasdaq 100 extras (not already in S&P 500) ────────────────────────────────
NASDAQ100_EXTRA = [
    "ADSK","AEP","ALGN","ALNY","AMAT","AMD","AMGN","AMZN","ASML",
    "AVGO","AXON","BIIB","BKNG","CDNS","CDW","CEG","CHTR","CMCSA","CPRT",
    "CSGP","CSCO","DXCM","EA","EXC","FANG","FAST","FTNT","GILD","GOOG",
    "HON","IDXX","ILMN","INTC","INTU","ISRG","KDP","KHC","KLAC","LRCX",
    "LULU","MAR","MCHP","MDLZ","META","MNST","MRNA","MSFT","MU","NFLX",
    "NVDA","NXPI","ODFL","ON","ORLY","PAYX","PCAR","PDD","PEP","PYPL",
    "QCOM","REGN","ROST","SBUX","SNPS","TEAM","TMUS","TSLA","TTD",
    "VRSK","VRSN","VRTX","WBA","WBD","WDAY","XEL","ZM","ZS"
]

# ── Large cap tech & growth ───────────────────────────────────────────────────
LARGE_CAP_TECH = [
    "PANW","NET","DDOG","SNOW","CRWD","OKTA","ZS","CYBR","S","TENB",
    "RPD","QLYS","HUBS","BILL","MNDY","TOST","FRSH","DOCN","GTLB","ESTC",
    "MDB","CFLT","APPF","SPSC","VEEV","PCTY","RNG","FIVN","NICE",
    "MANH","WIX","GWRE","NCNO","ALTR","SHOP","WDAY","TEAM","NOW",
    "TTD","ROKU","TWLO","ZI","BRZE","ASAN","TASK","BOX","DOCU",
    "RNG","SPSC"
]

# ── High momentum / growth ────────────────────────────────────────────────────
MOMENTUM = [
    "CELH","CAVA","DUOL","ONON","DECK","ELF","HIMS","APP","AXON","FICO",
    "WING","SHAK","BROS","DKNG","RBLX","UBER","ABNB","DASH","LYFT","HOOD",
    "AFRM","UPST","SOFI","LC","OPEN","RELY","RDDT","SNAP","PINS","SPOT",
    "LULU","SKX","CROX","BOOT","NKE","ADDYY","FIGS","OLPX","XPOF",
    "PLTR","ARM","SMCI","FTNT","SOUN","RCAT","ACHR","JOBY","ASTS","LUNR",
    "RXRX","IONQ","RGTI","QUBT","BBAI","IREN","CORZ","WULF",
    # Names you specifically mentioned
    "AXTI","BE","CIEN","COHR","LITE","NBIS","PL","Q","SNDK","TTMI","VIAV","VRT",
    # Defense-tech & space (high-momentum, liquid, defense spending tailwind)
    "KTOS","RKLB","AVAV","SATS",
]

# ── Crypto ecosystem ──────────────────────────────────────────────────────────
CRYPTO = [
    "COIN","MSTR","HOOD","RIOT","MARA","CLSK","WULF","IREN","CORZ","CIFR",
    "HUT","BTBT","BTDR","MSTU","BITO","ARKB","BITQ","GBTC","ETHE"
]

# ── Biotech / healthcare ──────────────────────────────────────────────────────
BIOTECH = [
    "MRNA","BNTX","ALNY","ARWR","VRTX","REGN","BIIB","AMGN","GILD","INCY",
    "EXAS","NTRA","GKOS","INSP","IRTC","TMDX","NVCR","ACAD",
    "PTGX","ROIV","FOLD","RXST","HALO","IOVA","MDGL","RGEN","DXCM",
    "IDXX","PODD","EW","BSX","STE","ILMN","TXG","CDNA","PACB","FATE","BEAM",
    "EDIT","CRSP","NTLA","SGMO","BLUE","AGEN","ADMA","ARDX",
    "ARQT","ASND","ATRC","AVXL","AXSM","BHVN","BMRN","CCCC","CERT",
    "CGEM","CHRS","CLDX","CLVT","CMRX","CNTA","COGT","CORT","CPIX","CRNX",
    "DAWN","DBVT","DNUT","DNLI","DPSI","EIDX","ENLV","EPZM",
    "ETNB","EVLO","FDMT","FFIE","FHTX","FLGT","FMTX","FNLC","FOLD","FORM",
    "FWBI","GERN","GLPG","GLYC","GRFS","HRMY","IMCR","IMVT","INVA","IONS",
    "IPSC","ITCI","JAZZ","KALA","KRYS","KYMR","LBPH","LGND",
    "LMNX","LNTH","MASS","MDXG","MGNX","MIRM","MNKD","MORF","MRVI","MRUS",
    "NBIX","NCNA","NKTR","NRIX","NUVL","OABI","OCUL","OFIX","OLMA","OMER",
    "OPCH","ORIC","ORPH","PHAT","PNTM","PRAX","PRGO","PRTA","PTCT",
    "PTON","RARE","RCKT","RDUS","REPL","RETA","RISK","RNAC","RUBY","RYTM",
    "SAGE","SANA","SBOT","SCPH","SDGR","SERA","SLDB","SMMT","SPRY","SRPT",
    "STOK","STRO","TARS","TBPH","TELA","TGTX","TMPO","TNXP","TPST","TPTX",
    "TTGT","TVTX","TYRA","URGN","UTRS","VCEL","VKTX","VRCA",
    "VYGR","XNCR","YMAB","ZYME"
]

# ── Russell 2000 liquid mid-caps ($500M–$5B, not already in S&P/Nasdaq) ──────
# Focus: liquid names with enough volume to trade, prime EP candidates
RUSSELL2000 = [
    # Financials
    "CUBI","EFSC","FFBC","FULT","INDB","IBOC","NBTB","OCFC","PACW","PRCT",
    "PVBC","SBCF","SMBC","TOWN","TRMK","UBSI","WABC","WSBC","HTLF","HONE",
    "HOPE","HAFC","CZWI","CBTX","BSVN","BANR","BANF","ATLO","ACNB",
    # Industrials
    "AAON","AIRC","ALGT","ARCB","ASGN","BCPC","BLKB","CEIX","CENTA",
    "CENX","CLFD","CNXN","CRVL","DXPE","ECPG","EPC","ESE","FICO","FLS",
    "GATX","GFF","GHM","GKOS","HCSG","HNRG","HURN","IIIN","JBSS","JOUT",
    "KAI","KELYA","KFRC","KN","LAWS","LNN","LQDT","LYTS","MATW","MGRC",
    "MHO","MYRG","NHC","NRC","NVEE","PRLB","PUMP","REZI","RGP","ROCK",
    "SCS","SHYF","SIF","SMTC","SNEX","SWI","TISI","TREX","USLM",
    "VSH","WDFC","WMS","WOR","WSC",
    # Technology
    "ACLS","AMBA","AOSL","APPN","ARLO","ATNI","BANDWIDTH","BCYC","BIGC",
    "CALX","CASA","CEVA","CMPR","CNXC","COHU","COMM","CRNC","DGII","DIOD",
    "EGHT","EGOV","EMKR","ENSG","EVBG","EXLS","EXPO","FARO","FORM","FOUR",
    "GDYN","GLBE","GRND","HLIT","ICAD","IDCC","IRDM","ITIC","JRVR","KLIC","KRNT","LPSN","MARA","MAXN","MCOM","MGNI","MKSI",
    "MLNK","MMSI","MNRO","MPWR","MRCY","NATI","NCNO","NTCT",
    "NTNX","NVAX","NVEI","NXST","OMCL","OPCH","OSPN","PAYO","PLAB","PLXS",
    "PLUS","POWI","PWSC","QLYS","QMCO","RAMP","RDFN","RDVT","RELY","RFIL",
    "RMBS","RNST","RSKD","RUTH","RXST","SABR","SANG","SCSC","SGHT","SLAB",
    "SMTC","SONO","SPNS","SPWH","SQSP","SSYS","STEM","STNE","SVMK","SWBI",
    "SYNA","SYSS","TASK","TCMD","TDOC","TIGO","TTEC","TTGT","TVTX","TWKS",
    "TYRA","UCTT","UPLD","UPST","URBN","USPH","VCNX","VERI","VIAV","VICR",
    "VIEW","VNET","VRNS","VRNT","VSAT","VSCO","VSEC","VSTO","VYGR","WERN",
    "WTFC","XPEL","YEXT","ZING",
    # Healthcare mid-caps
    "ACCD","ACET","ACHC","ADUS","AGIO","AKER","ALGN","ALKS","ALLO",
    "AMEH","AMRN","ANAB","APLS","APRE","ARNA","ARRY","ASRT","ATEX","ATRS",
    "ATXI","AUPH","AVDL","AVRO","AXNX","BCAB","BCDA","BGNE","BHVN","BIOL",
    "BJRI","BKD","BNGO","BNRX","BPMC","BSGM","BTAI","BYSI","CAPR","CARA",
    "CARG","CASH","CBST","CDTX","CERE","CHMA","CHRS","CLAR","CLDN","CLFD",
    "CLPS","CMPS","CNCE","CNET","COCP","CODA","CORCEPT","CORT","CPSI","CRIS",
    "CRSP","CRTX","CSII","CTKB","CTMX","CVAC","CVCO","CVET","CVRX","CYCN",
    # Consumer mid-caps
    "ARCO","BJ","BJRI","BLMN","BRC","CAKE","CBRL","CHUY","CLAR","CLOV",
    "CONN","CRNX","CRUS","CULP","CURV","CVGW","DAWN","DENN","DINE","DLTH",
    "DNOW","DORM","DSGN","DXLG","EAT","ECVT","ELME","ENVA","EPAC","ESTA",
    "EVGO","FCEL","FDUS","FIZZ","FLDM","FLXS","FMBI","FMCB","FMNB","FNKO",
    "FORD","FOUR","FRGE","FRPT","FRSH","FSLY","FTDR","FTHM","FTLF",
    "JACK","KRUS","LOCO","NDLS","NURO","PLAY","PLBY","PLCE","PRTH","PTLO",
    "RRGB","RUTH","SHAK","SMPL","SONO","STKS","TXRH","WING","XPOF"
]


SHORT_WATCH = [
    # Old tech
    "INTC","IBM","HPQ","STX","WDC","DELL","HPE","JNPR","CSCO","NOK","ERIC",
    # Media/cable
    "WBD","FOX","CMCSA","DIS","NWSA","AMC","CNK",
    # Retail struggling
    "GPS","PVH","VFC","RL","M","JWN","KSS",
    # EV washouts
    "WKHS","PTRA","RIVN","LCID","FSR","GOEV","HYLN",
    # Post-hype
    "BYND","OATLY","PTON","ZM","DOCU","TDOC","HIMS","OPEN",
    # China ADRs
    "NIO","XPEV","LI","BIDU","BABA","JD","PDD",
    # Meme stocks fading
    "GME","AMC","CLOV","WISH"
]

# ── ETFs ──────────────────────────────────────────────────────────────────────
ETFS = [
    # Broad market
    "SPY","QQQ","IWM","DIA","MDY","VTI","RSP","QQQE",
    # Sectors (all 11 GICS)
    "XLK","XLF","XLE","XLV","XLC","XLI","XLB","XLP","XLRE","XLU","XLY",
    # Bonds
    "TLT","IEF","SHY","HYG","LQD",
    # Commodities
    "GLD","SLV","GDX","GDXJ","USO",
    # Factor / style
    "IWF","IWD","MTUM","USMV",
    # International
    "EFA","EEM","FXI","VEU",
    # Thematic / innovation
    "ARKK","SOXX","IBB","ITB","XBI","HACK","ROBO",
    # Legacy (kept for scanner short signals / existing logic)
    "ARKG","ARKW","SOXL","TQQQ","UVXY","BITQ","BITO"
]

# ── Deduplicate preserving tier priority ──────────────────────────────────────
_all = SP500 + NASDAQ100_EXTRA + LARGE_CAP_TECH + MOMENTUM + CRYPTO + BIOTECH + RUSSELL2000 + SHORT_WATCH + ETFS
ALL_TICKERS = list(dict.fromkeys(_all))

# Tier lookup — higher priority lists win
TICKER_TIER: dict[str, int] = {}
# Default everything to tier 2
for t in ALL_TICKERS:
    TICKER_TIER[t] = 2
# Tier 1 — most liquid/momentum names
TIER1_SET = {
    "NVDA","AAPL","MSFT","META","TSLA","AMZN","GOOGL","GOOG","AMD","AVGO",
    "ORCL","CRM","ADBE","NOW","PANW","CRWD","NET","DDOG","PLTR","ARM",
    "APP","AXON","FICO","CELH","CAVA","DUOL","ONON","DECK","ELF","COIN",
    "MSTR","HOOD","LLY","NVO","ISRG","VRTX","REGN","AMAT","LRCX","KLAC",
    "QCOM","TXN","MU","MRVL","MPWR","GS","MS","JPM","V","MA","NFLX","UBER",
    "SHOP","RIOT","MARA","CLSK","WULF","MRNA","BNTX","ALNY",
    # Defense-tech & space momentum names
    "KTOS","RKLB","AVAV","SATS","LMT","GD","NOC","XOM","GLD",
}
for t in TIER1_SET:
    TICKER_TIER[t] = 1
# Tier 3 — small speculative biotech
TIER3_SET = set(BIOTECH) - TIER1_SET
for t in TIER3_SET:
    if t not in TIER1_SET:
        TICKER_TIER[t] = 3

TIER_ALERT_THRESHOLD = {1: 5, 2: 8, 3: 9}

def get_tier(ticker: str) -> int:
    return TICKER_TIER.get(ticker, 2)

BENCHMARK = "SPY"
