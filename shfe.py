import pandas as pd
import requests
import threading
from io import StringIO
from concurrent.futures import ThreadPoolExecutor, as_completed

dates = pd.date_range(start='2026-04-01', end='2026-04-28', freq='D')
thread_local = threading.local()                     # Create a 'thread-local' object to hold data specific to each thread.
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
max_workers = 10

def get_session():                                   # Define a function to get a session object for the current thread.
    if not hasattr(thread_local, "session"):         # If "thread_local" doesn't yet have a "session" attribute...
        thread_local.session = requests.Session()    # then, create one and assign it to thread_local.session
        thread_local.session.headers.update(headers) # Assign headers to the session object, previously defined in headers.
    return thread_local.session

def fetch_prices_data(date): 
    url = f"https://www.shfe.com.cn/data/tradedata/future/dailydata/kx{date.strftime('%Y%m%d')}.dat"
    response = get_session().get(url)
    print(response.status_code, "Price", date.strftime('%Y-%m-%d'))

def fetch_stocks_data(date):
    url = f"https://www.shfe.cn/data/tradedata/future/stockdata/weeklystock_{date.strftime('%Y%m%d')}/EN/all.html"
    response = get_session().get(url)
    print(response.status_code, "Stock", date.strftime('%Y-%m-%d'))

def fetch_shfe_data(date):
    fetch_prices_data(date)
    fetch_stocks_data(date)

def main():
    with ThreadPoolExecutor(max_workers=max_workers) as executor: # Create a pool with No. of workers in max_workers
        futures = [executor.submit(fetch_shfe_data, date) for date in dates]
        for future in as_completed(futures):
            None

if __name__ == "__main__":
    main()