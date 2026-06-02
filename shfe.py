import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import threading
import time
import logging
import os
from io import StringIO
from concurrent.futures import ThreadPoolExecutor, as_completed

os.makedirs("stocks", exist_ok=True)                    # If doesn't exist, create the "stocks" directory
os.makedirs("prices", exist_ok=True)                    # If doesn't exist, create the "prices" directory
trading_days = pd.bdate_range(start='2026-01-01', end='2026-06-02')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
request_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
thread_local = threading.local()                        # Create a 'thread-local' object to hold data specific to each thread.

def get_session() -> requests.Session:                  # Get a session object attached only to the current thread
    if not hasattr(thread_local, "session"):            # If "thread_local" doesn't yet have a 'session' object
        session = requests.Session()                    # 'session' object
        session.headers.update(request_headers)         # Assign the 'request_headers' to 'session'
        retries = Retry(total=3,                        # retry strategy
            backoff_factor=0.5,                         # Waiting time growth factor between retries: 0.5,1,2,4...
            status_forcelist=[429, 500, 502, 503, 504], # HTTP status codes that should trigger retries
            allowed_methods=["HEAD", "GET", "OPTIONS"], # HTTP methods that should trigger retries
            raise_on_status=False)                      # Don't raise exeptions. We'll handle them manually.
        adapter = HTTPAdapter(max_retries=retries)      # 'adapter' object that will manage retries
        session.mount("https://", adapter)              # Mount the 'adapter' to the 'session'
        session.mount("http://", adapter)
        thread_local.session = session                  # Assign the 'session' object to 'thread_local'
    return thread_local.session 

def fetch_prices_data(date) -> pd.DataFrame:            # Fetch prices for a give date and deliver a DataFrame
    url = f"https://www.shfe.cn/data/tradedata/future/dailydata/kx{date.strftime('%Y%m%d')}.dat"
    try: 
        response = get_session().get(url)
        if response.status_code == 404:
            logging.info("Price data not available for %s [404]", date.strftime('%d-%m-%Y'))
            return pd.DataFrame()
        response.raise_for_status()

        data = response.json()                                          # Parse the JSON response into a Python dictionary
        df = pd.DataFrame(data["o_curinstrument"])                      # Part of the raw_data is converted into a DataFrame
        
        df["group"] = pd.factorize(df["PRODUCTGROUPID"])[0]             # Create a 'group' column containing the group's number
        df.sort_values(["group", "DELIVERYMONTH"], kind="stable", inplace=True) # Sort by 'group' and 'DELIVERYMONTH'
        df.drop(columns=["group"], inplace=True)                        # Drop the temporary 'group' column
        df.reset_index(drop=True, inplace=True)                         # Reset the index of the DataFrame
        
        df.insert(0, "M", df.groupby("PRODUCTGROUPID").cumcount() + 1)  # Create 'M' column with cumulative count of rows within each group
        subtotal_rows = df.groupby("PRODUCTGROUPID").tail(1).index      # Get the index of the last row of each group
        df.loc[subtotal_rows, "M"] = 0                                  # Set 'M' value to 0 for subtotal rows

        with open(f"prices/{date.strftime('%Y.%m.%d')} SHFE prices.csv", 'w', newline='', encoding='utf-8-sig') as f:
            f.write(f'"# Date: {pd.to_datetime(data["report_date"]).strftime("%Y-%m-%d")}" \n') # Metadata
            f.write(f'"# Issue No.({data["o_year_num"]}), {data["o_year"]}" \n')
            f.write(f'"# Total {data["o_total_num"]} Issues" \n')
            f.write(f'"# Total {data["o_trade_day"]} Trading Days" \n\n')
            df.to_csv(f, index=False)
        logging.info("Price data fetched and saved for %s: %d rows", date.strftime('%d-%m-%Y'), len(df))
        return df
    
    except requests.RequestException as network_error:
        logging.error("Network error for %s [%s]", date.strftime('%d-%m-%Y'), network_error)
        return pd.DataFrame({"Price_Error": [str(network_error)]})
    except Exception as processing_error:
        logging.error("Error processing price data for %s [%s]", date.strftime('%d-%m-%Y'), processing_error)
        return pd.DataFrame({"Price_Error": [str(processing_error)]})

def fetch_stocks_data(date) -> pd.DataFrame:                # Fetch stocks for a give date and deliver a DataFrame
    url = f"https://www.shfe.cn/data/tradedata/future/stockdata/weeklystock_{date.strftime('%Y%m%d')}/EN/all.html"
    try:
        response = get_session().get(url, timeout=10)
        if response.status_code == 404:
            logging.info("Stocks data not available for %s [404]", date.strftime('%d-%m-%Y'))
            return pd.DataFrame()
        response.raise_for_status()
        
        raw_data = pd.read_html(StringIO(response.text))    # Read all tables from the HTML response into a list of DataFrames
        
        cleaned_dfs = []
        notes = []
        for df in raw_data:
            # Flatten the df columns if they are MultiIndex, then rename columns that match the Dictionary
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [col[0] if col[0] == col [1] else f"{col[0]} ({col[1]})" for col in df.columns]
            renames= {"Grade" : "Crude",
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
                "Factory Depot" : "Warehouse"}
            df.rename(columns=renames, inplace=True)
            
            # Extract the unit_of_measure and commodity_name from the first row, if provided
            unit_of_measure = df.iat[0,-1]
            if isinstance(unit_of_measure, str) and "Unit：" in unit_of_measure:    # If the "Unit: " exists
                unit_of_measure = unit_of_measure.split("Unit：")[1].strip()
                commodity_name = df.iat[0,0]
                df.insert(0, "Commodity", commodity_name)                           # Create a 'Commodity' column
                df.insert(1, "Unit", unit_of_measure)                               # Create a 'Unit' column
                df.drop(df.index[0], inplace=True)                                  # Drop the first row
                df.replace("--", pd.NA, inplace=True)                               # Replace any occurrence of "--" with NaN
            
            columns = df.columns.to_list()
            # Convert columns that contain numeric data stored as strings to numeric types
            for col in columns:
                if df[col].dropna().astype(str).str.fullmatch(r"-?\d+(\.\d+)?").all():  # If all values are numeric
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # If 'Change' column exists, insert sufix from the previous column i.e. "Change (Last Week)"
            if "Change" in columns:
                i = columns.index("Change")
                df.columns.values[i] = f"Change {columns[i-1][columns[i-1].find('('):columns[i-1].find(')')+1]}"            

            # Append the df to 'cleaned_dfs' if it doesn't contain the especial "Expiring Warrants" table
            # 'Unit : (WGHTUNIT)' identifyes the "Expiring Warrants" table, which is saved separately with metadata
            if 'Unit : (WGHTUNIT)' not in columns:
                cleaned_dfs.append(df) if df.shape[1] > 1 else notes.append(df)
            else:
                note = notes[-1].to_string(index=False, header=False).strip()
                note = "\n".join(f'"# {line}"' for line in note.splitlines())
                with open(f"stocks/{date.strftime('%Y.%m.%d')} SHFE amount of expiring standard warrants.csv", 'w', newline='', encoding='utf-8-sig') as f:
                    f.write(note + "\n\n")
                    df.to_csv(f, index=False)
                logging.info("Amount of expiring standard warrants data fetched and saved for %s: %d rows", date.strftime('%d-%m-%Y'), len(df))

        # Concatenate all cleaned_dfs into a single DataFrame and save it to a CSV file with notes as metadata
        df_stocks = pd.concat(cleaned_dfs, ignore_index=True)
        note = "\n".join(f'"# {df.to_string(index=False, header=False).strip()}"' for df in notes[0:2])
        with open(f"stocks/{date.strftime('%Y.%m.%d')} SHFE stocks.csv", 'w', newline='', encoding='utf-8-sig') as f:
            f.write(note + "\n\n")
            df_stocks.to_csv(f, index=False)
        logging.info("SHFE stocks data fetched and saved for %s: %d rows", date.strftime('%d-%m-%Y'), len(df_stocks))
        return df_stocks

    except requests.RequestException as network_error:
        logging.error("Network error for %s [%s]", date.strftime('%d-%m-%Y'), network_error)
        return pd.DataFrame({"Stock_Error": [str(network_error)]})
    except Exception as processing_error:
        logging.error("Error processing stocks data for %s [%s]", date.strftime('%d-%m-%Y'), processing_error)
        return pd.DataFrame({"Stock_Error": [str(processing_error)]})

def fetch_shfe_data(date):
    fetch_prices_data(date)
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