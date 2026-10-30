# Data

**Source:** [Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii), UCI Machine Learning Repository (public).
All transactions of a UK-based online gift wholesaler between 1 Dec 2009 and 9 Dec 2011: 1,067,371 lines with invoice, product code, quantity, unit price, timestamp, customer and country.

The CSV is about 95 MB, so it isn't committed. UCI distributes it as an Excel file with one sheet per year. Convert it to the CSV this project reads:

```python
import pandas as pd
sheets = pd.read_excel("online_retail_II.xlsx", sheet_name=None, dtype={"Invoice": str, "StockCode": str})
pd.concat(sheets.values()).to_csv("data/raw/online_retail_II.csv", index=False)
```

The two sheets overlap on 1-9 Dec 2010; `sql/02_clean_sales.sql` removes the duplicate copy.
