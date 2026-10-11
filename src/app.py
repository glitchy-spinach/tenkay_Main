import streamlit as st
import requests
import pandas as pd
from google import genai


# The SEC requires a uniquely identifying User-Agent for all API calls
SEC_HEADERS = {"User-Agent": "MyStreamlitApp (admin@mywebsite.com)"}

client = genai.Client()

stream = client.interactions.create(
    model="gemini-3.8-flash",
    input="Hello.",
    stream=True,
)



@st.cache_data
def fetch_sec_companies():
    """Fetches the master list of SEC filers."""
    url = "https://www.sec.gov/files/company_tickers.json"
    response = requests.get(url, headers=SEC_HEADERS)
    response.raise_for_status()
    
    company_list = list(response.json().values())
    
    # Add a padded 10-digit CIK (Required for the submissions endpoint)
    for company in company_list:
        company['cik_padded'] = str(company['cik_str']).zfill(10)
        
    return company_list

@st.cache_data
def fetch_company_filings(cik_padded):
    """Fetches and parses 10-K and 10-Q filings for a specific company."""
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    response = requests.get(url, headers=SEC_HEADERS)
    response.raise_for_status()
    
    data = response.json()
    recent = data.get("filings", {}).get("recent", {})
    records = []
    
    if not recent:
        return records

    # The SEC returns parallel arrays. We iterate through the 'form' array 
    # and extract data from the same index in the other arrays.
    for i, form in enumerate(recent.get("form", [])):
        # Filter for quarterly and annual reports
        if form in ["10-K", "10-Q"]:
            accession_number = recent["accessionNumber"][i]
            primary_doc = recent["primaryDocument"][i]
            
            # To build the SEC archive URL, we need:
            # 1. CIK without leading zeros
            # 2. Accession number without dashes
            cik_int = str(int(cik_padded))
            accession_folder = accession_number.replace("-", "")
            
            # Construct the direct link to the HTML filing
            doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_folder}/{primary_doc}"
            
            records.append({
                "Form": form,
                "Filing Date": recent["filingDate"][i],
                "Report Date": recent["reportDate"][i],
                "Accession Number": accession_number,
                "Document Link": doc_url
            })
            
    return records

def main():
    st.set_page_config(page_title="SEC 10-K/10-Q Explorer", layout="wide")
    st.title("SEC EDGAR 10-K & 10-Q Explorer")
    
    # 1. Fetch Company List
    with st.spinner("Fetching SEC company master list..."):
        companies = fetch_sec_companies()
        
    # Create a mapping dictionary for the dropdown (e.g., "AAPL - Apple Inc.")
    company_options = {f"{c['ticker']} - {c['title']}": c for c in companies}
    
    # 2. User selects a company
    st.subheader("1. Select a Company")
    selected_key = st.selectbox(
        "Search by Ticker or Name:", 
        options=list(company_options.keys())
    )
    
    selected_company = company_options[selected_key]
    
    # 3. Fetch and display filings
    st.subheader(f"2. Filings for {selected_company['title']}")
    
    with st.spinner(f"Pulling SEC submissions for {selected_company['ticker']}..."):
        filings = fetch_company_filings(selected_company['cik_padded'])
        
    if filings:
        df = pd.DataFrame(filings)
        
        # Streamlit's st.dataframe allows us to configure columns. 
        # We configure the 'Document Link' column to render as a clickable URL.
        st.dataframe(
            df, 
            use_container_width=True,
            column_config={
                "Document Link": st.column_config.LinkColumn("Filing Document (Click to Open)")
            }
        )
    else:
        st.warning("No 10-K or 10-Q filings found for this company in the recent submissions data.")

if __name__ == "__main__":
    main()