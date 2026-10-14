import streamlit as st
import requests
import pandas as pd
from google import genai
import re

# The SEC requires a uniquely identifying User-Agent for all API calls
SEC_HEADERS = {"User-Agent": "MyStreamlitApp (admin@mywebsite.com)"}


@st.cache_resource
def get_genai_client(api_key: str = None):
    """Initializes and caches the Google GenAI client."""
    if api_key:
        return genai.Client(api_key=api_key)
    return genai.Client()


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


@st.cache_data(show_spinner=False)
def fetch_filing_content(doc_url: str) -> str:
    """Downloads raw filing document from SEC EDGAR."""
    response = requests.get(doc_url, headers=SEC_HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def clean_html_content(raw_html: str, max_chars: int = 1_500_000) -> str:
    """Strips HTML tags, scripts, and styles to extract clean filing text."""
    if len(raw_html) > max_chars:
        raw_html = raw_html[:max_chars]
        
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(raw_html, "html.parser")
        for tag in soup(["script", "style", "meta", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
    except Exception:
        # Fallback regex if BeautifulSoup is not installed
        cleaned = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", raw_html, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        text = cleaned

    lines = (line.strip() for line in text.splitlines())
    return "\n".join(chunk for chunk in lines if chunk)


@st.cache_data(show_spinner=False)
def generate_filing_summary(
    doc_url: str,
    form_type: str,
    company_name: str,
    filing_date: str,
    report_date: str,
    model_name: str = "gemini-3.8-flash",
    api_key: str = None
) -> str:
    """Fetches filing content and generates an AI summary with section headings."""
    raw_html = fetch_filing_content(doc_url)
    cleaned_text = clean_html_content(raw_html)
    
    # Truncate text to fit context window comfortably
    truncated_text = cleaned_text[:300000]
    
    prompt = f"""You are an expert senior financial analyst. Analyze and summarize the following SEC {form_type} filing for {company_name}.
Filing Date: {filing_date}
Period of Report: {report_date}

Generate a comprehensive, executive-ready summary. You MUST organize the summary into clear, distinct Markdown headings (###) for each important section:

### 1. Executive Summary & Overview
- High-level overview of the filing, top strategic takeaways, major milestones, and corporate direction.

### 2. Business Overview & Key Developments
- Core business operations, segment breakdowns, recent product/service launches, M&A, and market expansions.

### 3. Financial Performance & Key Operating Metrics
- Comprehensive review of revenue, net income, operating margins, earnings per share (EPS), cash flows, and balance sheet strength with YoY/QoQ comparisons.

### 4. Management's Discussion and Analysis (MD&A)
- Management's perspective on operating results, segment trends, liquidity, capital expenditure, and critical accounting estimates.

### 5. Key Risk Factors & Challenges
- Key business, competitive, macroeconomic, supply chain, and regulatory risks disclosed (especially from Item 1A / risk disclosures).

### 6. Legal Proceedings & Contingencies
- Any material lawsuits, regulatory investigations, compliance issues, or contingent liabilities.

### 7. Future Outlook, Guidance & Strategic Priorities
- Management's forward-looking guidance, projected growth drivers, market opportunities, and capital allocation priorities.

Please make the analysis detailed, professional, and well-structured with clear bullet points under each heading.

Filing Text:
{truncated_text}
"""

    client = get_genai_client(api_key=api_key if api_key else None)

    # 1. Try Interactions API with selected model
    try:
        interaction = client.interactions.create(
            model=model_name,
            input=prompt
        )
        if hasattr(interaction, "output_text") and interaction.output_text:
            return interaction.output_text
        if hasattr(interaction, "outputs") and interaction.outputs:
            return interaction.outputs[-1].text
        return str(interaction)
    except Exception as e:
        # Fallback models in case selected model name or interactions API requires an alternative
        fallback_models = [m for m in ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"] if m != model_name]
        
        for fb_model in fallback_models:
            try:
                interaction = client.interactions.create(
                    model=fb_model,
                    input=prompt
                )
                if hasattr(interaction, "output_text") and interaction.output_text:
                    return interaction.output_text
                if hasattr(interaction, "outputs") and interaction.outputs:
                    return interaction.outputs[-1].text
            except Exception:
                pass
                
        # Fallback to models.generate_content API
        for fb_model in [model_name] + fallback_models:
            try:
                response = client.models.generate_content(
                    model=fb_model,
                    contents=prompt
                )
                if hasattr(response, "text") and response.text:
                    return response.text
            except Exception:
                pass
        
        raise e


def main():
    st.set_page_config(page_title="SEC 10-K/10-Q Explorer & AI Summarizer", layout="wide")
    st.title("SEC EDGAR 10-K & 10-Q Explorer with AI Summaries")
    
    # Sidebar settings
    with st.sidebar:
        st.header("⚙️ Model Configuration")
        api_key_input = st.text_input(
            "Gemini API Key:",
            type="password",
            help="Optional if GEMINI_API_KEY is already set in your environment variables."
        )
        model_choice = st.selectbox(
            "Gemini Model:",
            options=["gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.0-flash"],
            index=0
        )
        st.markdown("---")
        st.markdown(
            "**About**\n\n"
            "This application retrieves SEC EDGAR 10-K (Annual) and 10-Q (Quarterly) filings "
            "and generates AI-powered summaries with dedicated headings for all essential sections."
        )

    # Read query parameters for direct links
    query_ticker = st.query_params.get("ticker", "")
    query_accession = st.query_params.get("accession", "")
    
    # 1. Fetch Company List
    with st.spinner("Fetching SEC company master list..."):
        companies = fetch_sec_companies()
        
    # Create a mapping dictionary for the dropdown (e.g., "AAPL - Apple Inc.")
    company_options = {f"{c['ticker']} - {c['title']}": c for c in companies}
    
    # Default selection based on URL query param if present
    default_company_idx = 0
    if query_ticker:
        for idx, (label, comp) in enumerate(company_options.items()):
            if comp["ticker"].upper() == query_ticker.upper():
                default_company_idx = idx
                break

    # 2. User selects a company
    st.subheader("1. Select a Company")
    selected_key = st.selectbox(
        "Search by Ticker or Name:", 
        options=list(company_options.keys()),
        index=default_company_idx
    )
    
    selected_company = company_options[selected_key]
    
    # 3. Fetch and display filings
    st.subheader(f"2. Filings for {selected_company['title']} ({selected_company['ticker']})")
    
    with st.spinner(f"Pulling SEC submissions for {selected_company['ticker']}..."):
        filings = fetch_company_filings(selected_company['cik_padded'])
        
    if filings:
        df = pd.DataFrame(filings)
        
        # Append an extra column that links to the AI-generated summary
        df["AI Summary Link"] = df["Accession Number"].apply(
            lambda acc: f"/?ticker={selected_company['ticker']}&accession={acc}#ai-summary"
        )
        
        # Streamlit's st.dataframe allows us to configure columns. 
        # Both Document Link and AI Summary Link render as clickable URLs.
        st.dataframe(
            df, 
            width="stretch",
            column_config={
                "Document Link": st.column_config.LinkColumn("Filing Document (Click to Open)"),
                "AI Summary Link": st.column_config.LinkColumn(
                    "AI Summary",
                    display_text="View AI Summary"
                )
            }
        )

        st.markdown("<div id='ai-summary'></div>", unsafe_allow_html=True)
        st.subheader("3. AI-Generated Filing Summary")

        filing_labels = [
            f"{f['Form']} (Filed: {f['Filing Date']}, Period: {f['Report Date']}) - Acc: {f['Accession Number']}"
            for f in filings
        ]
        
        # Default filing to query param if provided
        default_filing_idx = 0
        if query_accession:
            for idx, f in enumerate(filings):
                if f["Accession Number"] == query_accession:
                    default_filing_idx = idx
                    break

        col_select, col_btn = st.columns([3, 1])
        with col_select:
            selected_filing_label = st.selectbox(
                "Select Filing to Summarize:",
                options=filing_labels,
                index=default_filing_idx
            )
        
        chosen_filing = filings[filing_labels.index(selected_filing_label)]
        
        with col_btn:
            st.write("")  # Vertical spacing
            generate_clicked = st.button("✨ Generate AI Summary", type="primary", width='stretch')

        summary_cache_key = f"summary_{chosen_filing['Accession Number']}"
        should_generate = generate_clicked or (query_accession == chosen_filing["Accession Number"])

        if should_generate and summary_cache_key not in st.session_state:
            with st.spinner(f"Fetching filing content and generating AI summary with section headings for {chosen_filing['Form']} ({chosen_filing['Filing Date']})..."):
                try:
                    summary_text = generate_filing_summary(
                        doc_url=chosen_filing["Document Link"],
                        form_type=chosen_filing["Form"],
                        company_name=selected_company["title"],
                        filing_date=chosen_filing["Filing Date"],
                        report_date=chosen_filing["Report Date"],
                        model_name=model_choice,
                        api_key=api_key_input.strip() if api_key_input else None
                    )
                    st.session_state[summary_cache_key] = summary_text
                except Exception as e:
                    st.error(f"Error generating AI summary: {e}")

        if summary_cache_key in st.session_state:
            summary = st.session_state[summary_cache_key]
            
            st.success(f"AI Summary for **{selected_company['title']}** - **{chosen_filing['Form']}** (Filing Date: {chosen_filing['Filing Date']})")
            
            col_meta1, col_meta2, col_meta3 = st.columns(3)
            col_meta1.metric("Form Type", chosen_filing["Form"])
            col_meta2.metric("Filing Date", chosen_filing["Filing Date"])
            col_meta3.metric("Report Date", chosen_filing["Report Date"])
            
            st.markdown(f"[📄 View Original SEC Document]({chosen_filing['Document Link']})")
            st.markdown("---")
            
            st.markdown(summary)
            
            st.download_button(
                label="📥 Download Summary as Markdown",
                data=summary,
                file_name=f"{selected_company['ticker']}_{chosen_filing['Form']}_{chosen_filing['Filing Date']}_summary.md",
                mime="text/markdown"
            )
        elif not should_generate:
            st.info("💡 Click **'View AI Summary'** in any table row above or click the **Generate AI Summary** button to generate a section-by-section breakdown.")

    else:
        st.warning("No 10-K or 10-Q filings found for this company in the recent submissions data.")


if __name__ == "__main__":
    main()