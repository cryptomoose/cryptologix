"""
Cryptocurrency configuration and metadata for CycleGeist
Contains the top 33 cryptocurrencies with their symbols and display names
"""

# Top 33 cryptocurrencies by market cap (as of 2025)
TOP_CRYPTOCURRENCIES = {
    "Bitcoin": "BTC-USD",
    "Ethereum": "ETH-USD", 
    "Tether": "USDT-USD",
    "BNB": "BNB-USD",
    "Solana": "SOL-USD",
    "XRP": "XRP-USD",
    "USDC": "USDC-USD",
    "Cardano": "ADA-USD",
    "Dogecoin": "DOGE-USD",
    "Avalanche": "AVAX-USD",
    "Tron": "TRX-USD",
    "Chainlink": "LINK-USD",
    "Polygon": "MATIC-USD",
    "Wrapped Bitcoin": "WBTC-USD",
    "Litecoin": "LTC-USD",
    "Shiba Inu": "SHIB-USD",
    "Bitcoin Cash": "BCH-USD",
    "Uniswap": "UNI-USD",
    "Near Protocol": "NEAR-USD",
    "Polkadot": "DOT-USD",
    "Internet Computer": "ICP-USD",
    "Ethereum Classic": "ETC-USD",
    "Stellar": "XLM-USD",
    "Cronos": "CRO-USD",
    "Monero": "XMR-USD",
    "Cosmos": "ATOM-USD",
    "Filecoin": "FIL-USD",
    "VeChain": "VET-USD",
    "Hedera": "HBAR-USD",
    "Algorand": "ALGO-USD",
    "ApeCoin": "APE-USD",
    "Fantom": "FTM-USD",
    "The Graph": "GRT-USD",
    "Worldcoin": "WLD-USD"
}

# Crypto categories for better organization
CRYPTO_CATEGORIES = {
    "Layer 1 Blockchains": ["Bitcoin", "Ethereum", "Solana", "Cardano", "Avalanche", "Tron", "Near Protocol", "Polkadot", "Stellar", "Cosmos", "Algorand", "Fantom", "Hedera"],
    "Layer 2 & Scaling": ["Polygon", "Internet Computer"],
    "DeFi & DEX": ["Uniswap", "Chainlink", "VeChain", "The Graph", "ApeCoin"],
    "AI & Identity": ["Worldcoin"],
    "Meme & Community": ["Dogecoin", "Shiba Inu"],
    "Wrapped & Stable": ["Wrapped Bitcoin", "Tether", "USDC"],
    "Exchange Tokens": ["BNB", "Cronos"],
    "Payments & Privacy": ["XRP", "Bitcoin Cash", "Litecoin", "Monero"],
    "Storage & Infrastructure": ["Filecoin", "Ethereum Classic"]
}

# Market cycle thresholds for different crypto types
CYCLE_THRESHOLDS = {
    "major_crypto": {  # BTC, ETH
        "extreme_bubble": 200,  # % gain from 200MA
        "bubble_forming": 150,
        "bull_market": 100,
        "accumulation": -20,
        "bear_market": -50,
        "extreme_bear": -70
    },
    "altcoins": {  # Most others
        "extreme_bubble": 300,
        "bubble_forming": 200,
        "bull_market": 150,
        "accumulation": -30,
        "bear_market": -60,
        "extreme_bear": -80
    },
    "stablecoins": {  # USDT, USDC
        "extreme_bubble": 5,
        "bubble_forming": 3,
        "bull_market": 2,
        "accumulation": -2,
        "bear_market": -3,
        "extreme_bear": -5
    }
}

def get_crypto_category(crypto_name):
    """Get the category of a cryptocurrency"""
    for category, cryptos in CRYPTO_CATEGORIES.items():
        if crypto_name in cryptos:
            return category
    return "Other"

def get_cycle_thresholds(crypto_name):
    """Get appropriate cycle thresholds for a cryptocurrency"""
    if crypto_name in ["Bitcoin", "Ethereum"]:
        return CYCLE_THRESHOLDS["major_crypto"]
    elif crypto_name in ["Tether", "USDC"]:
        return CYCLE_THRESHOLDS["stablecoins"]
    else:
        return CYCLE_THRESHOLDS["altcoins"]

def get_display_name(symbol):
    """Convert symbol back to display name"""
    for name, sym in TOP_CRYPTOCURRENCIES.items():
        if sym == symbol:
            return name
    return symbol.replace("-USD", "")