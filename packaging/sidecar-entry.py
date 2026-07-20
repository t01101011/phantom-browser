"""PyInstaller entry point: retain `python -m phantom.cli ...` argument parity."""
from phantom.cli import main

if __name__ == "__main__":
    main()
