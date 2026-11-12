"""Standalone runner for Trading 212 full transaction history export.
"""

from t212.history import export_history_to_csv

if __name__ == "__main__":
    export_history_to_csv()
