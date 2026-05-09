"""
ETH Fundamentals Fetcher
Fetches key on-chain metrics for Ethereum analysis:
- Total Value Locked (TVL) from DefiLlama
- Staking percentage from Beaconcha.in
- Fear & Greed Index from Alternative.me
- ETH/BTC ratio from Yahoo Finance
"""
import requests
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ETHFundamentals:
    """Fetches and caches ETH fundamental metrics from various free APIs"""
    
    def __init__(self):
        self.cache = {}
        self.cache_duration = 21600  # 6 hour cache matches Streamlit cache layer
    
    def _is_cache_valid(self, key):
        if key not in self.cache:
            return False
        cached_time = self.cache.get(f"{key}_time")
        if cached_time is None:
            return False
        age = (datetime.now() - cached_time).total_seconds()
        return age < self.cache_duration
    
    def get_ethereum_tvl(self):
        """Get Ethereum TVL from DefiLlama API"""
        cache_key = "eth_tvl"
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]
        
        try:
            url = "https://api.llama.fi/v2/chains"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            eth_data = next((chain for chain in data if chain.get('name') == 'Ethereum'), None)
            if eth_data:
                tvl = eth_data.get('tvl', 0)
                self.cache[cache_key] = tvl
                self.cache[f"{cache_key}_time"] = datetime.now()
                logger.info(f"DefiLlama ETH TVL: ${tvl/1e9:.2f}B")
                return tvl
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch ETH TVL: {e}")
            return self.cache.get(cache_key)
    
    def get_staking_stats(self):
        """Get ETH staking statistics via CoinGecko"""
        cache_key = "staking_stats"
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]
        
        try:
            url = "https://api.coingecko.com/api/v3/coins/ethereum"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            market_data = data.get('market_data', {})
            circulating = market_data.get('circulating_supply', 120_500_000)
            
            staked_eth = 32_000_000  # Approximate staked ETH
            staking_pct = (staked_eth / circulating) * 100
            
            stats = {
                'validators': staked_eth // 32,
                'staked_eth': staked_eth,
                'staking_pct': staking_pct,
                'total_supply': circulating
            }
            self.cache[cache_key] = stats
            self.cache[f"{cache_key}_time"] = datetime.now()
            logger.info(f"Staking: {staking_pct:.1f}% (CoinGecko estimate)")
            return stats
        except Exception as e:
            logger.warning(f"Failed to fetch staking stats: {e}")
            return self.cache.get(cache_key)
    
    def get_fear_greed_index(self):
        """Get Crypto Fear & Greed Index from Alternative.me"""
        cache_key = "fear_greed"
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]
        
        try:
            url = "https://api.alternative.me/fng/?limit=1"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('data'):
                fng_data = data['data'][0]
                result = {
                    'value': int(fng_data.get('value', 50)),
                    'classification': fng_data.get('value_classification', 'Neutral'),
                    'timestamp': fng_data.get('timestamp')
                }
                self.cache[cache_key] = result
                self.cache[f"{cache_key}_time"] = datetime.now()
                logger.info(f"Fear & Greed: {result['value']} ({result['classification']})")
                return result
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch Fear & Greed index: {e}")
            return self.cache.get(cache_key)
    
    def get_eth_btc_ratio(self):
        """Get ETH/BTC ratio"""
        cache_key = "eth_btc_ratio"
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]
        
        try:
            import yfinance as yf
            btc = yf.Ticker("BTC-USD")
            eth = yf.Ticker("ETH-USD")
            
            btc_price = btc.fast_info.get('lastPrice') or btc.fast_info.get('last_price')
            eth_price = eth.fast_info.get('lastPrice') or eth.fast_info.get('last_price')
            
            if btc_price and eth_price:
                ratio = eth_price / btc_price
                result = {
                    'ratio': ratio,
                    'eth_price': eth_price,
                    'btc_price': btc_price
                }
                self.cache[cache_key] = result
                self.cache[f"{cache_key}_time"] = datetime.now()
                logger.info(f"ETH/BTC Ratio: {ratio:.5f}")
                return result
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch ETH/BTC ratio: {e}")
            return self.cache.get(cache_key)
    
    def get_all_fundamentals(self):
        """Get all ETH fundamental metrics in one call"""
        return {
            'tvl': self.get_ethereum_tvl(),
            'staking': self.get_staking_stats(),
            'fear_greed': self.get_fear_greed_index(),
            'eth_btc': self.get_eth_btc_ratio(),
            'timestamp': datetime.now()
        }


def render_eth_fundamentals_card(st):
    """Render ETH fundamentals as a Streamlit component"""
    import streamlit as st_module
    
    @st_module.cache_data(ttl=21600)
    def fetch_fundamentals():
        fetcher = ETHFundamentals()
        return fetcher.get_all_fundamentals()
    
    fundamentals = fetch_fundamentals()
    
    st.markdown("### ETH Fundamentals")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        tvl = fundamentals.get('tvl')
        if tvl:
            st.metric(
                "Total Value Locked",
                f"${tvl/1e9:.1f}B",
                help="Total value locked in Ethereum DeFi protocols (DefiLlama)"
            )
        else:
            st.metric("Total Value Locked", "N/A")
    
    with col2:
        staking = fundamentals.get('staking')
        if staking:
            st.metric(
                "ETH Staked",
                f"{staking['staking_pct']:.1f}%",
                help=f"{staking['staked_eth']/1e6:.1f}M ETH locked in {staking['validators']:,} validators"
            )
        else:
            st.metric("ETH Staked", "N/A")
    
    with col3:
        fng = fundamentals.get('fear_greed')
        if fng:
            value = fng['value']
            classification = fng['classification']
            if value <= 25:
                color = "🔴"
            elif value <= 45:
                color = "🟠"
            elif value <= 55:
                color = "🟡"
            elif value <= 75:
                color = "🟢"
            else:
                color = "🟢"
            st.metric(
                "Fear & Greed",
                f"{color} {value}",
                help=f"Market sentiment: {classification}"
            )
        else:
            st.metric("Fear & Greed", "N/A")
    
    with col4:
        eth_btc = fundamentals.get('eth_btc')
        if eth_btc:
            ratio = eth_btc['ratio']
            st.metric(
                "ETH/BTC Ratio",
                f"{ratio:.4f}",
                help="Ethereum price relative to Bitcoin"
            )
        else:
            st.metric("ETH/BTC Ratio", "N/A")
