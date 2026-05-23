import pandas as pd
import requests

response = requests.get (f"https://www.shfe.com.cn/data/tradedata/future/dailydata/kx20260522.dat")

data = response.json()
df = pd.DataFrame(data['o_curinstrument'])

df["product_group_index"] = pd.factorize(df["PRODUCTGROUPID"])[0] # Create a new column with the group index

df = df.sort_values(["product_group_index", "DELIVERYMONTH"], ascending=[True, True], kind='stable') # Sort by group index and delivery month
df.drop(columns=["product_group_index"], inplace=True) # Remove the temporary group index column
df.reset_index(drop=True, inplace=True) # Reset the index after sorting

df.insert(0,"M",df.groupby("PRODUCTGROUPID").cumcount() + 1) # Add a new column "M" with the cumulative count of rows within each group, starting from 1
sub_totals_index = df.groupby("PRODUCTGROUPID").tail(1).index # Get the index of the last row of each group which turns to be the subtotal row
df.loc[sub_totals_index, "M"] = 0 # Set the "M" value to 0 for the subtotal rows

df.to_csv("shfe_prices.csv", index=False, encoding="utf-8-sig")