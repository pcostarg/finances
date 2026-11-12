import argparse
import sys
from t212.client import validate_credentials
from t212.history import export_history_to_csv
from t212.portfolio import export_portfolio_to_csv


def print_banner():
    print("=" * 54)
    print("             Trading 212 Export Tool              ")
    print("=" * 54)


def interactive_menu():
    validate_credentials()
    while True:
        print_banner()
        print("1. Export Portfolio Holdings (Qualtrim CSV)")
        print("2. Export Transaction History (Full Account Activity)")
        print("3. Export Both")
        print("0. Exit")
        print("-" * 54)

        try:
            choice = input("Select an option [1-3, 0]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if choice == "1":
            print("\n--- Running Portfolio Holdings Export ---")
            export_portfolio_to_csv()
            print()
        elif choice == "2":
            print("\n--- Running Full History Export ---")
            export_history_to_csv()
            print()
        elif choice == "3":
            print("\n--- Running Both Exports ---")
            export_portfolio_to_csv()
            print()
            export_history_to_csv()
            print()
        elif choice == "0":
            print("Goodbye!")
            break
        else:
            print("\n[!] Invalid selection. Please choose 1, 2, 3, or 0.\n")


def main():
    parser = argparse.ArgumentParser(
        description="Trading 212 data export utility for portfolio holdings and full transaction history.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-p",
        "--portfolio",
        action="store_true",
        help="Export current open portfolio holdings with weighted avg price (Qualtrim CSV).",
    )
    group.add_argument(
        "-H",
        "--history",
        action="store_true",
        help="Export full account transaction history (orders, dividends, transactions, interest).",
    )
    group.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Export both portfolio holdings and full transaction history.",
    )

    parser.add_argument(
        "--from",
        dest="time_from",
        metavar="DATE",
        help="Start date/time for history export (e.g. '2020-01-01' or '2020-01-01T00:00:00Z').",
    )
    parser.add_argument(
        "--to",
        dest="time_to",
        metavar="DATE",
        help="End date/time for history export (defaults to current time).",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output_file",
        metavar="FILENAME",
        help="Custom output CSV filename.",
    )

    args = parser.parse_args()

    # If no flags are provided, launch interactive menu
    if len(sys.argv) == 1:
        interactive_menu()
        return

    validate_credentials()

    if args.portfolio:
        export_portfolio_to_csv(output_filename=args.output_file)
    elif args.history:
        export_history_to_csv(
            output_filename=args.output_file,
            time_from=args.time_from,
            time_to=args.time_to,
        )
    elif args.all:
        print("\n--- Exporting Portfolio Holdings ---")
        export_portfolio_to_csv()
        print("\n--- Exporting Transaction History ---")
        export_history_to_csv(time_from=args.time_from, time_to=args.time_to)


if __name__ == "__main__":
    main()
