# Companies that Market Pulse will monitor
WATCHLIST = {
    "Nvidia": {
        "ticker": "NVDA",
        "cik": "0001045810"
    },
    "Microsoft": {
        "ticker": "MSFT",
        "cik": "0000789019"
    },
    "Alphabet": {
        "ticker": "GOOGL",
        "cik": "0001652044"
    },
    "Amazon": {
        "ticker": "AMZN",
        "cik": "0001018724"
    },
    "Apple": {
        "ticker": "AAPL",
        "cik": "0000320193"
    }
}


SEC_HEADERS = {
    "User-Agent": "Market Pulse 2003yicheng@gmail.com",
    "Accept-Encoding": "gzip, deflate"
}


# Filings we want to collect
WANTED_FORMS = {
    "8-K",
    "10-Q",
    "10-K"
}


# Number of filings to show for each company
MAX_FILINGS_PER_COMPANY = 5
