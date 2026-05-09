class DCASettings:
    def __init__(self):
        self.enabled = False
        self.baseline_per_day_usd = 100
        self.pair = ["BTC", "ETH"]
        self.mode = "equal"
        self.rebalance_cadence = "monthly"
        self.cap_floor = {"min": 0.30, "max": 0.70}
        self.normalize_annual_spend = True
        self.download_artifacts = True

    def to_dict(self):
        return {
            "enabled": self.enabled,
            "baseline_per_day_usd": self.baseline_per_day_usd,
            "pair": self.pair,
            "mode": self.mode,
            "rebalance_cadence": self.rebalance_cadence,
            "cap_floor": self.cap_floor,
            "normalize_annual_spend": self.normalize_annual_spend,
            "download_artifacts": self.download_artifacts,
        }

class Settings:
    def __init__(self):
        self.dca = DCASettings()

settings = Settings()
