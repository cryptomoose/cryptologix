"""
Overview/Explainer content for cryptologix investment thesis
"""
import streamlit as st

def render_overview_tab():
    """Render the introduction and investment thesis explanation"""
    
    # Investment Thesis Section
    st.markdown("## 🎯 Investment Thesis")
    
    st.markdown("""
    **cryptologix** implements an **exponential cycling strategy** designed to maximize wealth accumulation 
    through strategic rotations between asset classes at market extremes.
    
    ### Core Principle
    The platform answers one critical question: **WHEN should I rotate between crypto and precious metals?**
    
    By timing rotations at statistical extremes rather than holding through full cycles, you can achieve 
    exponential gains through the formula:
    """)
    
    st.latex(r"\text{Portfolio Value} = P_0 \times M^n")
    
    st.markdown("""
    Where:
    - **P₀** = Initial portfolio value
    - **M** = Multiplier per complete cycle (typically 1.5x - 3x)
    - **n** = Number of complete cycles
    
    **Example:** Starting with $10,000 and achieving a conservative 2x multiplier per cycle:
    - After 3 cycles: $10,000 × 2³ = **$80,000**
    - After 5 cycles: $10,000 × 2⁵ = **$320,000**
    - After 7 cycles: $10,000 × 2⁷ = **$1,280,000**
    """)
    
    # The Complete Cycle
    st.markdown("---")
    st.markdown("## 🔄 The Complete Exponential Cycle")
    
    # Visual cycle flow
    st.markdown("""
    <div style="background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); 
                padding: 2rem; border-radius: 20px; margin: 1.5rem 0;">
        <h3 style="color: white; text-align: center; margin-bottom: 1.5rem;">
            💵 USD → 🪙 BTC/ETH → 🥇 GOLD/SILVER → 💵 USD → 🔁 REPEAT
        </h3>
    </div>
    """, unsafe_allow_html=True)
    
    # Phase explanations
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        ### Phase 1: 🟢 ACCUMULATION
        **Market Percentile:** 5th - 45th  
        **Action:** Normal DCA at 1.2-1.7x multiplier  
        **Goal:** Build positions while crypto is undervalued
        
        ### Phase 2: 🟡 BULL MARKET
        **Market Percentile:** 45th - 75th
        **Action:** Baseline DCA at 1.0x multiplier
        **Goal:** Maintain discipline, avoid FOMO

        ### Phase 3: 🔴 EXTREME TOP
        **Market Percentile:** >85th
        **Action:** Rotate 85-90% out of crypto — 70% metals (gold 70% / silver 30%) + 30% stablecoins (Aave/sDAI)
        **Goal:** Lock in gains, preserve capital

        ### Phase 3.5: 🟠 BULL REDUCE
        **Market Percentile:** 75-85th | **Action:** Stop DCA, prepare rotation | **Goal:** Maximize exit price
        """)
    
    with col2:
        st.markdown("""
        ### Phase 4: 🥇 GOLD HOLDING
        **Market State:** Holding precious metals  
        **Action:** Wait patiently for crypto bottom  
        **Goal:** Preserve value during correction
        
        ### Phase 5: 🟠 EXTREME BOTTOM
        **Market Percentile:** <5th (with gold holdings)  
        **Action:** Liquidate gold → USD  
        **Goal:** Prepare capital for aggressive buying
        
        ### Phase 6: 🚀 AGGRESSIVE DCA
        **Market Percentile:** <15th (with USD available)  
        **Action:** Deploy at 2-3x multipliers  
        **Goal:** Maximum accumulation at bottom
        """)
    
    # Mathematical Foundation
    st.markdown("---")
    st.markdown("## 📐 How Rotation Percentages Are Calculated")
    
    st.markdown("""
    The app uses a **Kelly Criterion-inspired formula** to determine optimal rotation percentages 
    when recommending crypto → precious metals rotations.
    """)
    
    # Formula breakdown
    st.markdown("""
    ### The Formula
    """)
    
    st.latex(r"\text{Rotation\%} = \text{edge} \times \text{percentile\_strength} \times \text{confidence} \times 100")
    
    st.markdown("""
    ### Components Explained
    
    **1. Edge (0-1):** Signal strength combining multiple technical indicators
    - 40% weight: Current percentile position
    - 30% weight: RSI (Relative Strength Index)
    - 20% weight: Moving average crossover
    - 10% weight: Bollinger Bands position
    
    **2. Percentile Strength (0-1):** How extreme is the overvaluation
    - Only activates when crypto >85th percentile
    - Strength = (current_percentile - 85) / 15
    - Example: 95th percentile = (95-85)/15 = 0.67 strength
    
    **3. Confidence Multiplier:** Based on indicator convergence
    - **Very High** (1.0): All 4 indicators aligned
    - **High** (0.8): 3 indicators aligned
    - **Medium** (0.6): 2 indicators aligned
    - **Low** (0.4): 1 or fewer indicators aligned
    """)
    
    # Safety limits
    st.info("""
    **🛡️ Built-in Safety Limits:**
    - **Maximum rotation:** 75% (never rotate entire portfolio)
    - **Minimum threshold:** 10% (below this, recommendation = 0%)
    - **Trigger condition:** Only recommends rotations when crypto >85th percentile
    """)
    
    # Worked example
    st.markdown("### 📊 Worked Example")
    
    st.markdown("""
    **Scenario:** Bitcoin at 95th percentile, Very High confidence, +4.0 signal score
    
    **Calculation:**
    - Edge = 4.0 / 5.0 = **0.80**
    - Percentile Strength = (95 - 85) / 15 = **0.67**
    - Confidence Multiplier = **1.0** (Very High)
    - Rotation% = 0.80 × 0.67 × 1.0 × 100 = **53.6%**
    
    **Recommendation:** Rotate approximately **54% of your Bitcoin** into gold to lock in gains 
    while maintaining upside exposure with the remaining 46%.
    """)
    
    # BTC/ETH Allocation
    st.markdown("---")
    st.markdown("## ⚖️ BTC vs ETH Allocation (Within Crypto)")
    
    st.markdown("""
    While the rotation optimizer determines **WHEN** to move between crypto and precious metals, 
    a separate **Kelly Half Criterion** system optimizes your allocation **within** your crypto position.
    
    **Formula:** BTC Weight = 0.5 × (BTC_edge / Total_edge) + 0.25
    
    **Key Points:**
    - Uses relative percentiles as proxy for edge
    - Dynamic allocation based on current market conditions
    - Conservative bounds: **30-70%** BTC (never all-in on one asset)
    - Complements rotation strategy without conflicts
    
    **Example:** If BTC is at 60th percentile and ETH at 40th percentile:
    - BTC gets higher allocation (more favorable position)
    - If BTC at 30th and ETH at 70th → ETH gets higher allocation
    """)
    
    # Key Principles
    st.markdown("---")
    st.markdown("## 💡 Key Strategic Principles")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        ### 🎯 Emotionless Discipline
        Follow the data, not emotions. The system removes fear and greed from decisions.
        """)
    
    with col2:
        st.markdown("""
        ### 📊 Mathematical Rigor
        All recommendations backed by statistical analysis and historical percentiles.
        """)
    
    with col3:
        st.markdown("""
        ### 🛡️ Conservative Limits
        Built-in safety mechanisms prevent overexposure and preserve capital.
        """)
    
    # Inviolable DCA Floor
    st.markdown("---")
    st.info("""
    **💪 The Inviolable DCA Floor**
    
    Your weekly DCA amount ($777 default) is a **minimum commitment** that is never reduced - only scaled up. 
    This ensures consistent accumulation even during profit-taking periods. Multipliers range from:
    - **1.0x** (baseline during bull markets)
    - **1.2-1.7x** (accumulation phase)
    - **2.0-3.0x** (extreme opportunities at bottoms)
    
    This discipline is what transforms ordinary investing into exponential wealth building.
    """)
    
    # Final Note
    st.markdown("---")
    st.success("""
    **🚀 Ready to Begin?**
    
    Navigate to the **📊 DCA Strategy** tab to see your current cycle phase and this week's recommended action, 
    or explore **🥇 Gold Analysis** and **🥈 Silver Analysis** for detailed rotation recommendations.
    """)
