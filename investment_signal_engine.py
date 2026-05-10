import pandas as pd
import numpy as np
import logging
import streamlit as st
from long_term_data_fetcher import LongTermDataFetcher
from dca_enhancements import DCAEnhancementEngine, DCAEnhancementConfig
from config.settings import settings
import disk_cache

class InvestmentSignalEngine:
    """
    Core engine for generating clear, emotionless investment signals
    based on BTC/ETH vs Gold relative valuations
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.fetcher = LongTermDataFetcher()
        
        # Initialize DCA enhancement engine
        dca_config = DCAEnhancementConfig(settings.dca.to_dict())
        self.dca_engine = DCAEnhancementEngine(dca_config)
    
    @st.cache_data(ttl=0, show_spinner=False)
    def compute_usd_percentiles(_self):
        """
        Calculate pure BTC/USD and ETH/USD percentiles (independent of metals)
        These are used for DCA Strategy tab to show where crypto prices are vs historical USD prices
        Updates 24/7 with live crypto prices (no dependency on gold market hours)
        """
        logger = logging.getLogger(__name__)

        cached = disk_cache.load('usd_percentiles', max_age_hours=24)
        if cached is not None:
            return cached

        try:
            fetcher = LongTermDataFetcher()
            
            # Fetch crypto data with intraday updates
            btc_data = fetcher.get_comprehensive_crypto_data('BTC-USD')
            eth_data = fetcher.get_comprehensive_crypto_data('ETH-USD')
            
            if btc_data is None or eth_data is None:
                logger.error("Failed to fetch crypto data for USD percentiles")
                return None
            
            # Validate data freshness
            btc_fresh, btc_age, btc_ts = fetcher.validate_data_freshness(btc_data, 'BTC-USD', max_age_hours=36)
            eth_fresh, eth_age, eth_ts = fetcher.validate_data_freshness(eth_data, 'ETH-USD', max_age_hours=36)
            
            # Get USD prices with 2-year (730-day) rolling window for statistical soundness
            # This handles non-stationary crypto data by comparing against recent market regime
            btc_usd_prices = btc_data['Close'].dropna()
            eth_usd_prices = eth_data['Close'].dropna()
            
            # Time-based filter for exactly 730 calendar days (not 730 rows)
            import pandas as pd
            ROLLING_WINDOW_DAYS = 730
            cutoff_date = btc_usd_prices.index.max() - pd.Timedelta(days=ROLLING_WINDOW_DAYS)
            
            btc_usd_prices_window = btc_usd_prices[btc_usd_prices.index >= cutoff_date]
            eth_usd_prices_window = eth_usd_prices[eth_usd_prices.index >= cutoff_date]
            
            if len(btc_usd_prices_window) < 50 or len(eth_usd_prices_window) < 50:
                logger.error(f"Insufficient USD price data in 2-year window: BTC {len(btc_usd_prices_window)}, ETH {len(eth_usd_prices_window)}")
                return None
            
            # Calculate percentiles: where does current price rank vs 2-year rolling window?
            btc_usd_percentile = (btc_usd_prices_window <= btc_usd_prices_window.iloc[-1]).mean() * 100
            eth_usd_percentile = (eth_usd_prices_window <= eth_usd_prices_window.iloc[-1]).mean() * 100
            
            # Log percentiles and date range for transparency
            window_start = btc_usd_prices_window.index[0].date()
            window_end = btc_usd_prices_window.index[-1].date()
            logger.info(f"USD Percentiles (2-year window {window_start} to {window_end}, {len(btc_usd_prices_window)} days): BTC {btc_usd_percentile:.1f}%, ETH {eth_usd_percentile:.1f}%")
            
            result = {
                'btc_usd_percentile': btc_usd_percentile,
                'eth_usd_percentile': eth_usd_percentile,
                'btc_current_price': btc_usd_prices.iloc[-1],
                'eth_current_price': eth_usd_prices.iloc[-1],
                'btc_timestamp': btc_ts,
                'eth_timestamp': eth_ts,
                'btc_age_hours': btc_age,
                'eth_age_hours': eth_age,
                'btc_fresh': btc_fresh,
                'eth_fresh': eth_fresh,
                'btc_data_days': len(btc_usd_prices),
                'eth_data_days': len(eth_usd_prices)
            }
            disk_cache.save('usd_percentiles', result)
            return result
            
        except Exception as e:
            logger.error(f"USD percentile calculation failed: {e}")
            return None
    
    @st.cache_data(ttl=0, show_spinner=False)
    def calculate_relative_valuation_scores(_self):
        """
        Calculate relative valuation scores for BTC/ETH vs Gold with extreme market top detection
        Returns normalized scores where:
        - Positive = crypto overvalued vs gold (consider taking profits)
        - Negative = crypto undervalued vs gold (consider accumulating)
        """
        logger = logging.getLogger(__name__)

        cached = disk_cache.load('relative_valuation', max_age_hours=24)
        if cached is not None:
            return cached

        try:
            # Use the improved data fetcher with intraday support
            fetcher = LongTermDataFetcher()
            
            # Fetch data with intraday integration
            btc_data = fetcher.get_comprehensive_crypto_data('BTC-USD')
            eth_data = fetcher.get_comprehensive_crypto_data('ETH-USD')
            gold_data = fetcher.get_comprehensive_gold_data()
            silver_data = fetcher.get_comprehensive_silver_data()
            
            if btc_data is None or eth_data is None or gold_data is None:
                logger.error("Failed to fetch required market data")
                return None
            
            # Validate data freshness
            btc_fresh, btc_age, btc_ts = fetcher.validate_data_freshness(btc_data, 'BTC-USD', max_age_hours=36)
            eth_fresh, eth_age, eth_ts = fetcher.validate_data_freshness(eth_data, 'ETH-USD', max_age_hours=36)
            gold_fresh, gold_age, gold_ts = fetcher.validate_data_freshness(gold_data, 'Gold', max_age_hours=72)
            
            # Validate silver freshness (same threshold as gold - futures market)
            if silver_data is not None:
                silver_fresh, silver_age, silver_ts = fetcher.validate_data_freshness(silver_data, 'Silver', max_age_hours=72)
            else:
                silver_fresh, silver_age, silver_ts = False, 999, None
            
            if not btc_fresh or not eth_fresh:
                logger.warning(f"⚠️ Stale crypto data - BTC: {btc_age:.1f}h, ETH: {eth_age:.1f}h")
                
            # Normalize timezones
            for data in [btc_data, eth_data, gold_data]:
                if data.index.tz is not None:
                    try:
                        data.index = data.index.tz_localize(None)
                    except TypeError:
                        pass  # Already tz-naive
            
            # Find overlapping dates
            start_date = max(btc_data.index.min(), eth_data.index.min(), gold_data.index.min())
            end_date = min(btc_data.index.max(), eth_data.index.max(), gold_data.index.max())
            
            # Get aligned closing prices
            btc_prices = btc_data.loc[start_date:end_date]['Close']
            eth_prices = eth_data.loc[start_date:end_date]['Close']
            gold_prices = gold_data.loc[start_date:end_date]['Close']
            
            # Calculate ratios
            btc_gold_ratio = (btc_prices / gold_prices).dropna()
            eth_gold_ratio = (eth_prices / gold_prices).dropna()
            
            if len(btc_gold_ratio) < 50 or len(eth_gold_ratio) < 50:
                logger.error(f"Insufficient data: BTC {len(btc_gold_ratio)}, ETH {len(eth_gold_ratio)}")
                return None
            
            # Apply 2-year (730-day) rolling window to gold ratios for statistical soundness
            # Use time-based filter for exactly 730 calendar days
            import pandas as pd
            ROLLING_WINDOW_DAYS = 730
            gold_cutoff_date = btc_gold_ratio.index.max() - pd.Timedelta(days=ROLLING_WINDOW_DAYS)
            
            btc_gold_ratio_window = btc_gold_ratio[btc_gold_ratio.index >= gold_cutoff_date]
            eth_gold_ratio_window = eth_gold_ratio[eth_gold_ratio.index >= gold_cutoff_date]
            
            # Calculate GOLD RATIO percentile scores (0-100) - for gold rotation decisions
            btc_gold_percentile = (btc_gold_ratio_window <= btc_gold_ratio_window.iloc[-1]).mean() * 100
            eth_gold_percentile = (eth_gold_ratio_window <= eth_gold_ratio_window.iloc[-1]).mean() * 100
            
            # Calculate SILVER RATIO percentile scores (0-100) - for silver rotation decisions
            btc_silver_percentile = None
            eth_silver_percentile = None
            if silver_data is not None:
                try:
                    # Normalize silver data timezone
                    if silver_data.index.tz is not None:
                        try:
                            silver_data.index = silver_data.index.tz_localize(None)
                        except TypeError:
                            pass
                    
                    # Use same aligned date range as gold for consistency
                    # (start_date and end_date were already calculated from btc/eth/gold overlap)
                    silver_prices = silver_data.loc[start_date:end_date]['Close']
                    
                    # Calculate silver ratios using already-aligned crypto prices
                    btc_silver_ratio = (btc_prices / silver_prices).dropna()
                    eth_silver_ratio = (eth_prices / silver_prices).dropna()
                    
                    if len(btc_silver_ratio) >= 50 and len(eth_silver_ratio) >= 50:
                        # Apply 2-year (730-day) rolling window to silver ratios
                        # Use time-based filter for exactly 730 calendar days
                        silver_cutoff_date = btc_silver_ratio.index.max() - pd.Timedelta(days=ROLLING_WINDOW_DAYS)
                        
                        btc_silver_ratio_window = btc_silver_ratio[btc_silver_ratio.index >= silver_cutoff_date]
                        eth_silver_ratio_window = eth_silver_ratio[eth_silver_ratio.index >= silver_cutoff_date]
                        
                        btc_silver_percentile = (btc_silver_ratio_window <= btc_silver_ratio_window.iloc[-1]).mean() * 100
                        eth_silver_percentile = (eth_silver_ratio_window <= eth_silver_ratio_window.iloc[-1]).mean() * 100
                        logger.info(f"Silver Ratio Percentiles (2-year window {btc_silver_ratio_window.index[0].date()} to {btc_silver_ratio_window.index[-1].date()}, {len(btc_silver_ratio_window)} days): BTC {btc_silver_percentile:.1f}%, ETH {eth_silver_percentile:.1f}%")
                    else:
                        logger.warning(f"Insufficient silver ratio data: BTC {len(btc_silver_ratio)}, ETH {len(eth_silver_ratio)} points (need >=50)")
                except Exception as e:
                    logger.error(f"Failed to calculate silver percentiles: {e}")
            
            # Also calculate pure USD percentiles for DCA decisions
            usd_percentiles = _self.compute_usd_percentiles()
            usd_percentile_source = 'usd'
            if usd_percentiles is None:
                logger.error("Failed to compute USD percentiles, falling back to gold ratios — DCA tab will show gold-ratio percentiles")
                btc_usd_percentile = btc_gold_percentile
                eth_usd_percentile = eth_gold_percentile
                usd_percentile_source = 'gold_ratio_fallback'  # Propagated to result for UI warning
            else:
                btc_usd_percentile = usd_percentiles['btc_usd_percentile']
                eth_usd_percentile = usd_percentiles['eth_usd_percentile']
            
            # Signals based on USD percentiles (for DCA decisions)
            # Use canonical _percentile_to_signal method for consistent -5 to +5 mapping
            btc_signal = _self._percentile_to_signal(btc_usd_percentile)
            eth_signal = _self._percentile_to_signal(eth_usd_percentile)
            
            # Log percentiles with date ranges for transparency
            gold_window_start = btc_gold_ratio_window.index[0].date()
            gold_window_end = btc_gold_ratio_window.index[-1].date()
            
            logger.info(f"USD Percentiles (DCA): BTC {btc_usd_percentile:.1f}% (signal {btc_signal}), ETH {eth_usd_percentile:.1f}% (signal {eth_signal})")
            logger.info(f"Gold Ratio Percentiles (2-year window {gold_window_start} to {gold_window_end}, {len(btc_gold_ratio_window)} days): BTC {btc_gold_percentile:.1f}%, ETH {eth_gold_percentile:.1f}%")
            
            result = {
                # DCA signals and percentiles (based on USD)
                'btc_signal': btc_signal,
                'eth_signal': eth_signal,
                'btc_percentile': btc_usd_percentile,  # USD percentile for DCA tab
                'eth_percentile': eth_usd_percentile,  # USD percentile for DCA tab
                
                # Gold rotation percentiles (based on gold ratios) - for Gold Analysis tab
                'btc_gold_percentile': btc_gold_percentile,
                'eth_gold_percentile': eth_gold_percentile,
                'btc_current_ratio': btc_gold_ratio.iloc[-1],
                'eth_current_ratio': eth_gold_ratio.iloc[-1],
                
                # Silver rotation percentiles (based on silver ratios) - for Silver Analysis tab
                'btc_silver_percentile': btc_silver_percentile,
                'eth_silver_percentile': eth_silver_percentile,
                
                # Metadata
                'data_days': len(btc_gold_ratio),
                'date_range': f"{start_date.date()} to {end_date.date()}",
                
                # Data freshness information
                'btc_timestamp': btc_ts,
                'eth_timestamp': eth_ts,
                'gold_timestamp': gold_ts,
                'btc_age_hours': btc_age,
                'eth_age_hours': eth_age,
                'gold_age_hours': gold_age,
                'btc_fresh': btc_fresh,
                'eth_fresh': eth_fresh,
                'gold_fresh': gold_fresh,
                # Silver freshness information
                'silver_timestamp': silver_ts,
                'silver_age_hours': silver_age,
                'silver_fresh': silver_fresh,
                # USD percentile data source — 'usd' normally, 'gold_ratio_fallback' if USD fetch failed
                'usd_percentile_source': usd_percentile_source
            }
            disk_cache.save('relative_valuation', result)
            return result
            
        except Exception as e:
            logger.error(f"Signal calculation failed: {e}")
            return None
    
    def _calculate_technical_extremes(self, btc_data, eth_data, gold_data):
        """
        Calculate technical indicators to identify extreme market tops
        """
        try:
            # RSI calculations (14-period)
            def calculate_rsi(prices, period=14):
                delta = prices.diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
                rs = gain / loss
                return 100 - (100 / (1 + rs))
            
            btc_rsi = calculate_rsi(btc_data['Close']).iloc[-1]
            eth_rsi = calculate_rsi(eth_data['Close']).iloc[-1]
            
            # Bollinger Band position (20-period, 2 std dev)
            def bollinger_position(prices, period=20, std_dev=2):
                sma = prices.rolling(window=period).mean()
                std = prices.rolling(window=period).std()
                upper_band = sma + (std * std_dev)
                lower_band = sma - (std * std_dev)
                current_price = prices.iloc[-1]
                return (current_price - lower_band.iloc[-1]) / (upper_band.iloc[-1] - lower_band.iloc[-1])
            
            btc_bb_pos = bollinger_position(btc_data['Close'])
            eth_bb_pos = bollinger_position(eth_data['Close'])
            
            # Price velocity (30-day momentum)
            btc_momentum = (btc_data['Close'].iloc[-1] / btc_data['Close'].iloc[-30] - 1) * 100
            eth_momentum = (eth_data['Close'].iloc[-1] / eth_data['Close'].iloc[-30] - 1) * 100
            
            # Volume analysis (current vs 30-day average)
            btc_vol_ratio = btc_data['Volume'].iloc[-5:].mean() / btc_data['Volume'].iloc[-35:-5].mean()
            eth_vol_ratio = eth_data['Volume'].iloc[-5:].mean() / eth_data['Volume'].iloc[-35:-5].mean()
            
            return {
                'btc_technicals': {
                    'rsi': btc_rsi,
                    'bb_position': btc_bb_pos,
                    'momentum_30d': btc_momentum,
                    'volume_ratio': btc_vol_ratio
                },
                'eth_technicals': {
                    'rsi': eth_rsi,
                    'bb_position': eth_bb_pos,
                    'momentum_30d': eth_momentum,
                    'volume_ratio': eth_vol_ratio
                }
            }
            
        except Exception as e:
            self.logger.error(f"Technical calculation failed: {e}")
            return {
                'btc_technicals': {'rsi': 50, 'bb_position': 0.5, 'momentum_30d': 0, 'volume_ratio': 1},
                'eth_technicals': {'rsi': 50, 'bb_position': 0.5, 'momentum_30d': 0, 'volume_ratio': 1}
            }

    def _percentile_to_signal_with_technicals(self, percentile, technicals):
        """
        Convert percentile rank to -5 to +5 signal scale with technical confirmation
        Only triggers extreme signals (+4/+5) when technical indicators confirm extreme conditions
        """
        base_signal = self._percentile_to_signal(percentile)
        
        # Technical extreme conditions for "take profits" confirmation
        extreme_conditions = 0
        
        # RSI above 70 (overbought)
        if technicals['rsi'] > 70:
            extreme_conditions += 1
        if technicals['rsi'] > 80:
            extreme_conditions += 1
            
        # Bollinger Band position above 80% (near upper band)
        if technicals['bb_position'] > 0.8:
            extreme_conditions += 1
        if technicals['bb_position'] > 0.95:
            extreme_conditions += 1
            
        # Strong positive momentum (>50% in 30 days)
        if technicals['momentum_30d'] > 50:
            extreme_conditions += 1
        if technicals['momentum_30d'] > 100:
            extreme_conditions += 1
            
        # Volume surge (>2x recent average)
        if technicals['volume_ratio'] > 2:
            extreme_conditions += 1
        if technicals['volume_ratio'] > 3:
            extreme_conditions += 1
        
        # Only allow extreme positive signals with technical confirmation
        if base_signal >= 4:  # Very/extremely overvalued
            if extreme_conditions >= 4:  # Need 4+ technical confirmations
                return base_signal  # Keep extreme signal
            else:
                return min(base_signal, 2)  # Cap at moderately overvalued
        elif base_signal == 3:  # Overvalued
            if extreme_conditions >= 2:  # Need 2+ technical confirmations
                return base_signal
            else:
                return min(base_signal, 1)  # Cap at slightly overvalued
        
        return base_signal
    
    def _percentile_to_signal(self, percentile):
        """
        Convert percentile rank to -5 to +5 signal scale.
        Fair value band is symmetric: 40-60% = signal 0.
        Weighted signal uses 40% BTC / 60% ETH throughout.
        """
        if percentile >= 95:
            signal = 5   # Extremely overvalued (95%+)
        elif percentile >= 85:
            signal = 4   # Very overvalued (85-94%)
        elif percentile >= 75:
            signal = 3   # Overvalued (75-84%)
        elif percentile >= 65:
            signal = 2   # Moderately overvalued (65-74%)
        elif percentile >= 60:
            signal = 1   # Slightly overvalued (60-64%)
        elif percentile >= 40:
            signal = 0   # Fair value (40-59%) — symmetric 20pt window
        elif percentile >= 35:
            signal = -1  # Slightly undervalued (35-39%)
        elif percentile >= 25:
            signal = -2  # Moderately undervalued (25-34%)
        elif percentile >= 15:
            signal = -3  # Undervalued (15-24%)
        elif percentile >= 5:
            signal = -4  # Very undervalued (5-14%)
        else:
            signal = -5  # Extremely undervalued (0-4%)
        return signal
    
    def generate_daily_recommendation(self):
        """
        Generate clear, actionable daily investment recommendation
        """
        signals = self.calculate_relative_valuation_scores()
        if signals is None:
            return None
            
        btc_signal = signals['btc_signal']
        eth_signal = signals['eth_signal']
        
        # Determine primary action with weighted signal (40% BTC, 60% ETH)
        avg_signal = (0.4 * btc_signal + 0.6 * eth_signal)
        
        # Require BOTH assets to be in extreme territory for profit-taking
        both_extreme = btc_signal >= 4 and eth_signal >= 4
        
        if both_extreme and avg_signal >= 4:
            primary_action = "TAKE_PROFITS"
            action_color = "#FF4444"
            action_desc = "EXTREME TOP: Convert crypto positions to gold, maintain baseline DCA"
        elif avg_signal >= 2:
            primary_action = "MAINTAIN_BASELINE"
            action_color = "#FFA500"
            action_desc = "Maintain baseline DCA - market overvalued but continue accumulation"
        elif avg_signal >= -1:
            primary_action = "MAINTAIN_DCA"
            action_color = "#FFFF00"
            action_desc = "Continue normal baseline DCA schedule"
        elif avg_signal >= -2:
            primary_action = "INCREASE_DCA"
            action_color = "#90EE90"
            action_desc = "Increase DCA by 30% - favorable conditions"
        elif avg_signal >= -3:
            primary_action = "STRONG_INCREASE"
            action_color = "#32CD32"
            action_desc = "Increase DCA by 70% - strong buying opportunity"
        else:
            primary_action = "MAXIMUM_INCREASE"
            action_color = "#00FF00"
            action_desc = "Increase DCA by 150% - extreme accumulation opportunity"
            
        return {
            'primary_action': primary_action,
            'action_color': action_color,
            'action_description': action_desc,
            'btc_signal': btc_signal,
            'eth_signal': eth_signal,
            'combined_signal': avg_signal,
            'btc_percentile': signals['btc_percentile'],
            'eth_percentile': signals['eth_percentile'],
            'confidence': self._calculate_confidence(btc_signal, eth_signal),
            'technical_details': signals.get('technical_signals', {}),
            'data_quality': {
                'days': signals['data_days'],
                'range': signals['date_range']
            }
        }
    
    def _calculate_confidence(self, btc_signal, eth_signal):
        """Calculate confidence level based on signal alignment"""
        signal_diff = abs(btc_signal - eth_signal)
        
        if signal_diff <= 1:
            return "HIGH"
        elif signal_diff <= 2:
            return "MEDIUM"
        else:
            return "LOW"
    
    def get_position_sizing_recommendation(self, base_dca_amount=777, use_kelly=True, enhanced_settings=None):
        """
        Calculate recommended DCA amount based on signals using enhanced DCA or traditional logic
        """
        recommendation = self.generate_daily_recommendation()
        if recommendation is None:
            return None
        
        # Try enhanced DCA system first if enabled via session settings
        if enhanced_settings and enhanced_settings.get('enabled', False):
            try:
                enhanced_result = self._get_enhanced_dca_sizing_session(
                    base_dca_amount, recommendation, enhanced_settings
                )
                if enhanced_result:
                    return enhanced_result
            except Exception as e:
                self.logger.warning(f"Enhanced DCA failed, using fallback: {e}")
        
        # Fallback to existing Kelly/traditional logic
        signal = recommendation['combined_signal']
        
        if use_kelly:
            return self._get_kelly_based_sizing(base_dca_amount, recommendation)
        else:
            return self._get_traditional_sizing(base_dca_amount, recommendation)
    
    def _get_enhanced_dca_sizing(self, base_weekly_amount, recommendation):
        """
        Enhanced DCA sizing using seasonal/Kelly allocation modes with monthly optimization
        """
        try:
            import yfinance as yf
            
            # Fetch historical data for enhanced DCA analysis
            btc = yf.Ticker('BTC-USD')
            btc_data = btc.history(period='max', interval='1d')
            
            eth = yf.Ticker('ETH-USD')
            eth_data = eth.history(period='max', interval='1d')
            
            if btc_data.empty or eth_data.empty:
                self.logger.warning("Cannot fetch data for enhanced DCA")
                return None
            
            # Get current prices
            btc_price = btc_data['Close'].iloc[-1]
            eth_price = eth_data['Close'].iloc[-1]
            
            # Generate enhanced DCA advice
            enhanced_advice = self.dca_engine.generate_enhanced_dca_advice(
                btc_data, eth_data, btc_price, eth_price, base_weekly_amount
            )
            
            if not enhanced_advice.get('enabled', False):
                return None
            
            dca_advice = enhanced_advice['dca_advice']
            allocations = dca_advice['allocations']
            
            # Calculate total weekly amount based on monthly allocation
            weekly_multiplier = self._get_signal_multiplier(recommendation['combined_signal'])
            total_weekly_amount = base_weekly_amount * weekly_multiplier
            
            # Scale allocations to weekly amounts
            btc_alloc = next(a for a in allocations if a['asset'] == 'BTC')
            eth_alloc = next(a for a in allocations if a['asset'] == 'ETH')
            
            # Convert monthly to weekly (exact: 7/30) and apply signal multiplier
            btc_weekly = (btc_alloc['usd'] * 7 / 30) * weekly_multiplier
            eth_weekly = (eth_alloc['usd'] * 7 / 30) * weekly_multiplier

            return {
                'base_amount': base_weekly_amount,
                'multiplier': weekly_multiplier,
                'recommended_amount': total_weekly_amount,
                'btc_allocation': btc_weekly,
                'eth_allocation': eth_weekly,
                'btc_weight': btc_alloc['weight'],
                'eth_weight': eth_alloc['weight'],
                'action': recommendation['primary_action'],
                'action_note': f"Enhanced DCA: {dca_advice['rationale_summary']}",
                'method': f'enhanced_dca_{dca_advice["mode_used"]}',
                'enhanced_details': {
                    'mode_used': dca_advice['mode_used'],
                    'month': dca_advice['month'],
                    'monthly_spend': dca_advice['month_spend_usd'],
                    'data_quality': enhanced_advice['statistics']['data_sufficiency']
                }
            }

        except Exception as e:
            self.logger.error(f"Enhanced DCA calculation failed: {e}")
            return None

    def _get_signal_multiplier(self, signal):
        """
        Full Kelly-aligned DCA multiplier. No artificial floor — Kelly math
        determines sizing in both directions. 1/8 Kelly cap applied in
        KellyPositionSizer prevents extreme cuts. $777 is the base weekly amount.
        """
        if signal <= -4:
            return 2.5   # Extreme accumulation
        elif signal <= -2:
            return 1.7   # Strong increase
        elif signal <= -1:
            return 1.3   # Increase DCA
        elif signal < 1:
            return 1.0   # Fair value — baseline
        elif signal < 2:
            return 0.8   # Slightly overvalued — modest reduction
        elif signal < 4:
            return 0.5   # Overvalued — meaningful reduction
        else:
            return 0.1   # Extreme top — near-zero, Kelly says don't bet
    
    def _get_enhanced_dca_sizing_session(self, base_weekly_amount, recommendation, enhanced_settings):
        """
        Enhanced DCA sizing using session-specific settings to avoid global state issues
        """
        try:
            import yfinance as yf
            from dca_enhancements import DCAEnhancementEngine, DCAEnhancementConfig
            
            # Create session-specific DCA config
            dca_config_dict = {
                "enabled": True,
                "baseline_per_day_usd": enhanced_settings.get('baseline', 100),
                "pair": ["BTC", "ETH"],
                "mode": enhanced_settings.get('mode', 'equal'),
                "rebalance_cadence": "monthly",
                "cap_floor": {"min": 0.30, "max": 0.70},
                "normalize_annual_spend": True,
                "download_artifacts": True
            }
            
            # Create session-specific DCA engine
            dca_config = DCAEnhancementConfig(dca_config_dict)
            session_dca_engine = DCAEnhancementEngine(dca_config)
            
            # Fetch historical data for enhanced DCA analysis
            btc = yf.Ticker('BTC-USD')
            btc_data = btc.history(period='max', interval='1d')
            
            eth = yf.Ticker('ETH-USD')
            eth_data = eth.history(period='max', interval='1d')
            
            if btc_data.empty or eth_data.empty:
                self.logger.warning("Cannot fetch data for enhanced DCA")
                return None
            
            # Get current prices
            btc_price = btc_data['Close'].iloc[-1]
            eth_price = eth_data['Close'].iloc[-1]
            
            # Generate enhanced DCA advice
            enhanced_advice = session_dca_engine.generate_enhanced_dca_advice(
                btc_data, eth_data, btc_price, eth_price, base_weekly_amount
            )
            
            if not enhanced_advice.get('enabled', False):
                return None
            
            dca_advice = enhanced_advice['dca_advice']
            allocations = dca_advice['allocations']
            
            # Calculate total weekly amount based on market signals
            weekly_multiplier = self._get_signal_multiplier(recommendation['combined_signal'])
            total_weekly_amount = base_weekly_amount * weekly_multiplier
            
            # Scale allocations to weekly amounts
            btc_alloc = next(a for a in allocations if a['asset'] == 'BTC')
            eth_alloc = next(a for a in allocations if a['asset'] == 'ETH')
            
            # Convert monthly to weekly (exact: 7/30) and apply signal multiplier
            btc_weekly = (btc_alloc['usd'] * 7 / 30) * weekly_multiplier
            eth_weekly = (eth_alloc['usd'] * 7 / 30) * weekly_multiplier
            
            return {
                'base_amount': base_weekly_amount,
                'multiplier': weekly_multiplier,
                'recommended_amount': total_weekly_amount,
                'btc_allocation': btc_weekly,
                'eth_allocation': eth_weekly,
                'btc_weight': btc_alloc['weight'],
                'eth_weight': eth_alloc['weight'],
                'action': recommendation['primary_action'],
                'action_note': f"Enhanced DCA: {dca_advice['rationale_summary']}",
                'method': f'enhanced_dca_{dca_advice["mode_used"]}',
                'enhanced_details': {
                    'mode_used': dca_advice['mode_used'],
                    'month': dca_advice['month'],
                    'monthly_spend': dca_advice['month_spend_usd'],
                    'data_quality': enhanced_advice['statistics']['data_sufficiency']
                }
            }
            
        except Exception as e:
            self.logger.error(f"Session-based enhanced DCA calculation failed: {e}")
            return None
    
    def _get_kelly_based_sizing(self, base_dca_amount, recommendation):
        """
        Kelly Criterion based position sizing with direct data fetching
        """
        try:
            import yfinance as yf
            from kelly_position_sizing import KellyPositionSizer
            
            # Direct fetch for Kelly calculation
            btc = yf.Ticker('BTC-USD')
            btc_data = btc.history(period='1y', interval='1d')
            
            eth = yf.Ticker('ETH-USD')
            eth_data = eth.history(period='1y', interval='1d')
            
            if btc_data.empty or eth_data.empty:
                self.logger.warning("Cannot fetch data for Kelly calculation")
                return self._get_traditional_sizing(base_dca_amount, recommendation)
            
            # Calculate returns
            btc_returns = btc_data['Close'].pct_change().dropna()
            eth_returns = eth_data['Close'].pct_change().dropna()
            
            kelly_sizer = KellyPositionSizer()
            kelly_rec = kelly_sizer.get_kelly_based_dca_recommendation(
                base_dca_amount, btc_returns, eth_returns,
                recommendation['btc_signal'], recommendation['eth_signal']
            )
            
            return {
                'base_amount': base_dca_amount,
                'multiplier': kelly_rec['total_multiplier'],
                'recommended_amount': kelly_rec['total_dca'],
                'btc_allocation': kelly_rec['btc_allocation'],
                'eth_allocation': kelly_rec['eth_allocation'],
                'btc_weight': kelly_rec['btc_weight'],
                'eth_weight': kelly_rec['eth_weight'],
                'action': recommendation['primary_action'],
                'action_note': kelly_rec['explanation'],
                'kelly_metrics': kelly_rec['kelly_metrics'],
                'method': 'kelly_criterion'
            }
            
        except Exception as e:
            self.logger.warning(f"Kelly calculation failed, using traditional: {e}")
            return self._get_traditional_sizing(base_dca_amount, recommendation)
    
    def _get_traditional_sizing(self, base_dca_amount, recommendation):
        """
        Signal-based position sizing fallback (used when Kelly calculation fails).
        Full Kelly philosophy: sizing moves in both directions based on signal.
        Base weekly amount: $777.
        """
        signal = recommendation['combined_signal']

        if signal <= -4:
            multiplier = 2.5
            action_note = "Increase DCA 150% — extreme accumulation opportunity"
        elif signal <= -2:
            multiplier = 1.7
            action_note = "Increase DCA 70% — strong buying opportunity"
        elif signal <= -1:
            multiplier = 1.3
            action_note = "Increase DCA 30% — favorable conditions"
        elif signal < 1:
            multiplier = 1.0
            action_note = "Maintain baseline DCA — fair value"
        elif signal < 2:
            multiplier = 0.8
            action_note = "Reduce DCA 20% — slightly overvalued"
        elif signal < 4:
            multiplier = 0.5
            action_note = "Reduce DCA 50% — overvalued conditions"
        else:
            multiplier = 0.1
            action_note = "Minimal DCA — extreme top signal"

        recommended_amount = base_dca_amount * multiplier

        return {
            'base_amount': base_dca_amount,
            'multiplier': multiplier,
            'recommended_amount': recommended_amount,
            'action': recommendation['primary_action'],
            'action_note': action_note,
            'method': 'traditional_heuristic'
        }
    
    def generate_comprehensive_rotation_recommendation(self, btc_data, eth_data, gold_data, btc_percentile, eth_percentile):
        """
        Generate comprehensive rotation recommendation for BTC/ETH vs Gold
        Returns action, confidence, explanation and rotation percentage
        """
        try:
            # Calculate signal scores from percentiles (-5 to +5 scale)
            btc_signal = self._percentile_to_signal(btc_percentile)
            eth_signal = self._percentile_to_signal(eth_percentile)
            
            # Combined weighted signal (ETH weighted more heavily)
            combined_signal = (0.4 * btc_signal + 0.6 * eth_signal)
            
            # Determine action based on signal strength
            if combined_signal >= 3.5:
                action = "ROTATE_TO_GOLD"
                confidence = min(0.9, 0.5 + (combined_signal - 3.5) * 0.1)
                explanation = f"Crypto extremely overvalued vs gold (BTC: {btc_percentile:.1f}%, ETH: {eth_percentile:.1f}%)"
                rotation_percentage = min(50, 10 + (combined_signal - 3.5) * 15)
            elif combined_signal <= -3.5:
                action = "ROTATE_TO_CRYPTO"
                confidence = min(0.9, 0.5 + abs(combined_signal + 3.5) * 0.1)
                explanation = f"Crypto extremely undervalued vs gold (BTC: {btc_percentile:.1f}%, ETH: {eth_percentile:.1f}%)"
                rotation_percentage = min(50, 10 + abs(combined_signal + 3.5) * 15)
            else:
                action = "HOLD"
                confidence = 0.7
                explanation = f"Normal market conditions - continue DCA (BTC: {btc_percentile:.1f}%, ETH: {eth_percentile:.1f}%)"
                rotation_percentage = 0
            
            return {
                'action': action,
                'confidence': confidence,
                'explanation': explanation,
                'rotation_percentage': rotation_percentage,
                'btc_signal': btc_signal,
                'eth_signal': eth_signal,
                'combined_signal': combined_signal,
                'btc_percentile': btc_percentile,
                'eth_percentile': eth_percentile
            }
            
        except Exception as e:
            self.logger.error(f"Error generating rotation recommendation: {e}")
            return {
                'action': 'HOLD',
                'confidence': 0.5,
                'explanation': 'Unable to calculate rotation signals - continue normal DCA',
                'rotation_percentage': 0,
                'btc_signal': 0,
                'eth_signal': 0,
                'combined_signal': 0,
                'btc_percentile': 50,
                'eth_percentile': 50
            }
    
