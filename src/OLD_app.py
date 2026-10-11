from google import genai
import pandas as pd
import requests as rq
import json
import streamlit as st

USER_AGENT = "10k_Test surinac.se@gmail.com"
BASE_URL = "https://data.sec.gov"
SEC_BASE_URL = "https://sec.gov"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate"
}

# client = genai.Client()

# stream = client.interactions.create(
#     model="gemini-3.8-flash",
#     input="Count from 1 to 25.",
#     stream=True,
# )
# for event in stream:
#     print(event)
#     if event.event_type == "step.delta":
#         if event.delta.type == "text":
#             print(event.delta.text, end="", flush=True)

with open('assets\Main_Ticker.json', 'r')as f:
    data = json.load(f)

print(data)
