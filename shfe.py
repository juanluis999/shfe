import pandas as pd
import requests
import threading
from io import StringIO
from concurrent.futures import ThreadPoolExecutor, as_completed

dates = pd.date_range(start='2026-04-01', end='2026-04-28', freq='D')
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
thread_local = threading.local()                     # Create a 'thread-local' object to hold data specific to each thread.

def get_session() -> requests.Session:                  # Get a session object attached only to the current thread
    if not hasattr(thread_local, "session"):            # If "thread_local" doesn't yet have a 'session' object
        session = requests.Session()                    # 'session' object
        session.headers.update(headers)                 # Assign the 'headers' dict. to 'session'
        retries = requests.adapters.Retry(              # retry strategy
            total=3,
            backoff_factor=0.5,                         # Waiting time growth factor between retries: 0.5,1,2,4...
            status_forcelist=[429, 500, 502, 503, 504], # HTTP status codes that should trigger retries
            allowed_methods=["HEAD", "GET", "OPTIONS"], # HTTP methods that should trigger retries
            raise_on_status=False)                      # Don't raise exeptions. We'll handle them manually.
        adapter = requests.adapters.HTTPAdapter(max_retries=retries) # 'adapter' object that will manage retries
        session.mount("https://", adapter)              # Mount the 'adapter' to the 'session'
        session.mount("http://", adapter)
        thread_local.session = session                  # Assign the 'session' object to 'thread_local'
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
    with ThreadPoolExecutor(max_workers=10) as executor: # Create a pool with No. of workers in max_workers
        futures = [executor.submit(fetch_shfe_data, date) for date in dates] # 'futures' object store the threads and start them.
        for future in as_completed(futures):
            future.result()  # Show the result of each thread once completed.

if __name__ == "__main__":
    main()