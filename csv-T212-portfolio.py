"""Standalone runner for Trading 212 current portfolio holdings export.
Preserved for backward compatibility.
"""

from t212.portfolio import export_portfolio_to_csv

if __name__ == "__main__":
    export_portfolio_to_csv()
