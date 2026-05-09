"""
Persistent Storage Module for cryptologix
Handles saving/loading DCA history and portfolio state to local JSON file
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path


class PersistentStorage:
    """Manages persistent storage of DCA contributions and portfolio state"""
    
    def __init__(self, storage_file: str = "cryptologix_data.json"):
        self.storage_file = storage_file
        self.data = self._load_data()
        # Migrate legacy records after data is loaded
        self._migrate_legacy_records()
    
    def _load_data(self) -> Dict:
        """Load data from JSON file, create if doesn't exist"""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r') as f:
                    data = json.load(f)
                    return data
            except Exception as e:
                print(f"Error loading storage file: {e}")
                return self._create_default_data()
        else:
            return self._create_default_data()
    
    def _migrate_legacy_records(self) -> None:
        """Migrate legacy DCA records to new schema in-place"""
        if "dca_history" in self.data:
            migrated = False
            for i, record in enumerate(self.data["dca_history"]):
                # Check if record needs migration (missing total_usd field)
                if "total_usd" not in record:
                    self.data["dca_history"][i] = {
                        "date": record.get("date", datetime.now().isoformat()),
                        "total_usd": record.get("amount", 0),
                        "btc_usd": record.get("btc_usd", 0),
                        "eth_usd": record.get("eth_usd", 0),
                        "multiplier": record.get("multiplier", 1.0),
                        "reasoning": record.get("reasoning", "Legacy contribution"),
                        "timestamp": record.get("timestamp", record.get("date", datetime.now().isoformat()))
                    }
                    migrated = True
            
            # Save migrated data back to file
            if migrated:
                print(f"Migrated {sum(1 for r in self.data['dca_history'] if 'total_usd' in r)} legacy DCA records to new schema")
                self._save_data()
    
    def _create_default_data(self) -> Dict:
        """Create default data structure"""
        return {
            "dca_history": [],
            "portfolio_state": {
                "crypto_allocation": 0.0,
                "gold_allocation": 0.0,
                "silver_allocation": 0.0,
                "usd_available": 0.0,
                "rotation_history": []
            },
            "settings": {
                "base_weekly_dca": 777
            },
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            }
        }
    
    def _save_data(self) -> bool:
        """Save data to JSON file"""
        try:
            # Ensure metadata block exists (for legacy file compatibility)
            if "metadata" not in self.data:
                self.data["metadata"] = {
                    "created_at": datetime.now().isoformat()
                }
            
            self.data["metadata"]["last_updated"] = datetime.now().isoformat()
            with open(self.storage_file, 'w') as f:
                json.dump(self.data, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving storage file: {e}")
            return False
    
    # DCA History Methods
    def add_dca_contribution(self, dca_record: Dict) -> bool:
        """Add a DCA contribution to history with full details"""
        # Ensure date field exists
        if "date" not in dca_record:
            dca_record["date"] = datetime.now().isoformat()
        
        # Ensure timestamp exists
        if "timestamp" not in dca_record:
            dca_record["timestamp"] = datetime.now().isoformat()
        
        # Normalize schema for compatibility with UI expectations
        # Ensure all expected fields exist with defaults
        normalized_record = {
            "date": dca_record.get("date"),
            "total_usd": dca_record.get("total_usd", dca_record.get("amount", 0)),
            "btc_usd": dca_record.get("btc_usd", 0),
            "eth_usd": dca_record.get("eth_usd", 0),
            "multiplier": dca_record.get("multiplier", 1.0),
            "reasoning": dca_record.get("reasoning", ""),
            "timestamp": dca_record.get("timestamp")
        }
        
        self.data["dca_history"].append(normalized_record)
        return self._save_data()
    
    def get_dca_history(self) -> List[Dict]:
        """Get all DCA contributions with normalized schema"""
        raw_history = self.data.get("dca_history", [])
        normalized_history = []
        
        for record in raw_history:
            # Normalize each record to ensure all expected fields exist
            normalized = {
                "date": record.get("date", datetime.now().isoformat()),
                "total_usd": record.get("total_usd", record.get("amount", 0)),
                "btc_usd": record.get("btc_usd", 0),
                "eth_usd": record.get("eth_usd", 0),
                "multiplier": record.get("multiplier", 1.0),
                "reasoning": record.get("reasoning", "Legacy contribution"),
                "timestamp": record.get("timestamp", record.get("date", datetime.now().isoformat()))
            }
            normalized_history.append(normalized)
        
        return normalized_history
    
    def get_total_dca_contributions(self) -> float:
        """Calculate total DCA contributions"""
        total = 0.0
        for contrib in self.data.get("dca_history", []):
            # Handle both old and new schema
            total += contrib.get("total_usd", contrib.get("amount", 0))
        return total
    
    def get_dca_count(self) -> int:
        """Get number of DCA contributions"""
        return len(self.data.get("dca_history", []))
    
    # Portfolio State Methods
    def save_portfolio_state(self, crypto: float, gold: float, usd: float, silver_pct: float = 0.0) -> bool:
        """Save current portfolio state"""
        self.data["portfolio_state"]["crypto_allocation"] = crypto
        self.data["portfolio_state"]["gold_allocation"] = gold
        self.data["portfolio_state"]["silver_allocation"] = silver_pct
        self.data["portfolio_state"]["usd_available"] = usd
        return self._save_data()
    
    def get_portfolio_state(self) -> Dict:
        """Get current portfolio state"""
        return self.data.get("portfolio_state", {
            "crypto_allocation": 0.0,
            "gold_allocation": 0.0,
            "silver_allocation": 0.0,
            "usd_available": 0.0,
            "rotation_history": []
        })
    
    def add_rotation_to_history(self, rotation_data: Dict) -> bool:
        """Add a rotation event to history"""
        rotation_entry = {
            **rotation_data,
            "timestamp": datetime.now().isoformat()
        }
        
        if "rotation_history" not in self.data["portfolio_state"]:
            self.data["portfolio_state"]["rotation_history"] = []
        
        self.data["portfolio_state"]["rotation_history"].append(rotation_entry)
        return self._save_data()
    
    def get_rotation_history(self) -> List[Dict]:
        """Get all rotation events"""
        return self.data["portfolio_state"].get("rotation_history", [])
    
    # Settings Methods
    def save_base_weekly_dca(self, amount: float) -> bool:
        """Save base weekly DCA amount setting"""
        self.data["settings"]["base_weekly_dca"] = amount
        return self._save_data()
    
    def get_base_weekly_dca(self) -> float:
        """Get base weekly DCA amount setting"""
        return self.data["settings"].get("base_weekly_dca", 1111)
    
    # Utility Methods
    def clear_all_data(self) -> bool:
        """Clear all stored data (reset)"""
        self.data = self._create_default_data()
        return self._save_data()
    
    def export_data(self) -> Dict:
        """Export all data for backup"""
        return self.data.copy()
    
    def import_data(self, data: Dict) -> bool:
        """Import data from backup"""
        self.data = data
        return self._save_data()
    
    def get_summary_stats(self) -> Dict:
        """Get summary statistics"""
        total_dca = self.get_total_dca_contributions()
        dca_count = self.get_dca_count()
        portfolio = self.get_portfolio_state()
        
        return {
            "total_dca_invested": total_dca,
            "number_of_contributions": dca_count,
            "average_contribution": total_dca / dca_count if dca_count > 0 else 0,
            "current_crypto_value": portfolio.get("crypto_allocation", 0),
            "current_gold_value": portfolio.get("gold_allocation", 0),
            "current_usd_available": portfolio.get("usd_available", 0),
            "total_portfolio_value": (
                portfolio.get("crypto_allocation", 0) + 
                portfolio.get("gold_allocation", 0) + 
                portfolio.get("usd_available", 0)
            )
        }
