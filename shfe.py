import pandas as pd
import requests
import threading
import time
import logging
import os
from io import StringIO
from concurrent.futures import ThreadPoolExecutor, as_completed

trading_days = pd.bdate_range(start='2026-04-01', end='2026-04-28')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
request_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
thread_local = threading.local()                        # Create a 'thread-local' object to hold data specific to each thread.

def get_session() -> requests.Session:                  # Get a session object attached only to the current thread
    if not hasattr(thread_local, "session"):            # If "thread_local" doesn't yet have a 'session' object
        session = requests.Session()                    # 'session' object
        session.headers.update(request_headers)         # Assign the 'request_headers' to 'session'
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
    url = f"https://www.shfe.cn/data/tradedata/future/dailydata/kx{date.strftime('%Y%m%d')}.dat"
    response = get_session().get(url)
    logging.info("Price data fetched for %s: %d", date.strftime('%Y-%m-%d'), response.status_code)

def fetch_stocks_data(date): # Fetch stocks for a give date and deliver a DataFrame
    url = f"https://www.shfe.cn/data/tradedata/future/stockdata/weeklystock_{date.strftime('%Y%m%d')}/EN/all.html"
    try:
        response = get_session().get(url, timeout=10)
        if response.status_code == 404:
            logging.warning("Stocks data not available for %s [404]", date.strftime('%Y-%m-%d')) # or logging.info
            return pd.DataFrame()
        response.raise_for_status()
        
        data = pd.read_html(StringIO(response.text)) # Read all tables from the HTML response into a list of DataFrames
        
        df_stocks = pd.DataFrame() # Create an empty DataFrame to store the concatenated results
        for df in data:
            if isinstance(df.columns, pd.MultiIndex): # Flatten the df columns if they are MultiIndex
                df.columns = [col[0] if col[0] == col [1] else f"{col[0]} ({col[1]})" for col in df.columns]
            
            if "Change" in df.columns: # If 'Change' column exists, insert sufix from previous column: Change (Last Week)
                columns = df.columns.to_list()
                i = columns.index("Change")
                df.columns.values[i] = f"Change {columns[i-1][columns[i-1].find('('):columns[i-1].find(')')+1]}"
            
            renames= {
                "Theoretical Available Capacity (Last week)": "Storage Capacity (Last week)",
                "Theoretical Available Capacity (This Week)": "Storage Capacity (This Week)",
                "Theoretical Available Capacity (Change)": "Storage Capacity (Change)",
                "Storage of last week": "Previous Week (Delivery-able)",
                "Storage of this week": "This Week (Delivery-able)",
                "Storage Change": "Change (Delivery-able)",
                "Storage of last week (Delivery-able)": "Previous Week (Delivery-able)",
                "Storage of last week (On Warrant)": "Previous Week (On Warrant)",
                "Storage of this week (Delivery-able)": "This Week (Delivery-able)",
                "Storage of this week (On Warrant)": "This Week (On Warrant)",
                "Storage Change (Delivery-able)": "Change (Delivery-able)",
                "Storage Change (On Warrant)": "Change (On Warrant)",
                "Factory Warehouse" : "Warehouse",
                "Depot" : "Warehouse",
                "Grade" : "Crude",
                "Factory Depot" : "Warehouse"}
            df.rename(columns=renames, inplace=True) # Rename columns as per the 'renames' dictionary, if they exist.
            
            unit_of_measure = df.iloc[0,-1] # Get the last column of the first row which may contain the "Unit: " information
            if isinstance(unit_of_measure, str) and "Unit：" in unit_of_measure: # If the "Unit: " measurement is provided
                unit_of_measure = unit_of_measure.split("Unit：")[1].strip() # Extract the unit of measure
                commodity_name = df.iloc[0,0] # Get the first column of the first row which may contain the commodity name
                df.insert(0, "Commodity", f"{commodity_name} ({unit_of_measure})") #...Create a 'Commodity' column by extracting it from the first row's first column
                #df.insert(1, "Unit", unit_of_measure) #...Create a 'Unit' column by extracting it from the first row's last column
                df.drop(df.index[0], inplace=True) # Drop the first row which is now redundant after extracting the 'Unit' and 'Commodity' info.
                df.replace("--", pd.NA, inplace=True) #...Replace any occurrence of "--" with NaN
            
            # Convert columns that contain numeric data stored as strings to numeric types
            df = df.apply(lambda col: pd.to_numeric(col, errors='coerce') if col.dropna().astype(str).str.fullmatch(r"-?\d+(\.\d+)?").all() else col)
            
            if df.shape[1] > 1: # If the DataFrame has more than one column...
                df_stocks = pd.concat([df_stocks, df], ignore_index=True) # Concatenate the cleaned DataFrame to the main 'DF'
            
        os.makedirs("stocks", exist_ok=True) # If doesn't exist, create the "stocks" directory
        df_stocks.to_csv(f"stocks/{date.strftime('%Y.%m.%d')} SHFE stocks.csv", index=False)
        logging.info("SHFE stocks data fetched and saved for %s: %d rows", date.strftime('%d-%m-%Y'), len(df_stocks))
        return df_stocks

    except requests.RequestException as network_error:
        logging.error("Network error for %s [%s]", date.strftime('%d-%m-%Y'), network_error)
        return pd.DataFrame({"Stock_Error": [str(network_error)]})
    except Exception as processing_error:
        logging.error("Error processing stocks data for %s [%s]", date.strftime('%d-%m-%Y'), processing_error)
        return pd.DataFrame({"Stock_Error": [str(processing_error)]})

def fetch_shfe_data(date):
    #fetch_prices_data(date)
    fetch_stocks_data(date)

def main():
    start_time = time.time()
    logging.info("Starting data fetch for %d trading days.", len(trading_days))
    with ThreadPoolExecutor(max_workers=10) as executor: # Create a pool with 10 worker threads
        futures = [executor.submit(fetch_shfe_data, date) for date in trading_days] # 'futures' object store the threads and start them.
        for future in as_completed(futures):
            future.result()  # Show the result of each thread once completed.
    logging.info("Data fetch completed in %.2f seconds. JL 2026", time.time() - start_time)
if __name__ == "__main__":
    main()