import pandas as pd
import requests
import threading
from io import StringIO

dates = pd.date_range(start='2026-05-01', end='2026-05-28', freq='D')
thread_local = threading.local()                  # Create a thread-local storage object to hold data that is specific to each thread.
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}

def get_session():                                   # Define a function to get a session object for the current thread.
    if not hasattr(thread_local, "session"):         # If "thread_local" doesn't yet have a "session" attribute...
        thread_local.session = requests.Session()    # then, create one and assign it to thread_local.session
        thread_local.session.headers.update(HEADERS) # Assign headers to the session object, previously defined in HEADERS.
    return thread_local.session

def fetch_prices_data(date): 
    url = f"https://www.shfe.com.cn/data/tradedata/future/dailydata/kx{date.strftime('%Y%m%d')}.dat"
    response = get_session().get(url)
    print(response.status_code)

def fetch_stocks_data(date):
    url = f"https://www.shfe.cn/data/tradedata/future/stockdata/weeklystock_{date.strftime('%Y%m%d')}/EN/all.html"
    response = get_session().get(url)
    print(response.status_code)

def fetch_shfe_data(date):
    fetch_prices_data(date)
    fetch_stocks_data(date)
