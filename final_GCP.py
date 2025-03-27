from flask import Flask, request, render_template, jsonify
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
from google.cloud import storage
import io
import os
import re
import time

app = Flask(__name__)

# GCP configuration
GCP_BUCKET_NAME = "my-data-bucket-qinvst"
RAW_FILE = "output_combined.xlsx"
CLEANED_FILE = "cleaned_output_combined.xlsx"
GCP_CREDENTIALS_PATH = r"C:\Users\pande\OneDrive\Documents\keys\prismatic-night-454303-s1-412af151235d.json"

# Extract all sections by heading name
def extract_all_tables(driver):
    tables_data = []

    # Wait until at least one table is present
    WebDriverWait(driver, 15).until(EC.presence_of_all_elements_located((By.TAG_NAME, "table")))
    possible_headers = driver.find_elements(By.XPATH, "//*[contains(text(), 'Records')]")

    for header in possible_headers:
        text = header.text.strip()
        match = re.search(r"(Paid|Refused|In Hold)\s+Records", text, re.IGNORECASE)

        if match:
            record_type = match.group(1).strip().capitalize()

            try:
                # Get the next table after this header
                table = header.find_element(By.XPATH, "following::table[1]")

                # Extract column headers
                headers = [th.text.strip() for th in table.find_elements(By.TAG_NAME, "th")]
                rows = table.find_elements(By.TAG_NAME, "tr")

                data = []
                for row in rows:
                    cols = [col.text.strip() for col in row.find_elements(By.TAG_NAME, "td")]
                    if cols:
                        data.append(cols)

                if data:
                    df = pd.DataFrame(data, columns=headers)
                    df["Record_Type"] = record_type
                    tables_data.append(df)

            except Exception as e:
                print(f"Skipping section {text} due to error: {e}")
                continue

    return tables_data

# Main process function
def process_html_file(html_url):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)

    try:
        driver.get(html_url)
        time.sleep(2)  # optional: wait for JS-rendered content

        all_tables = extract_all_tables(driver)
        if not all_tables:
            return "No valid tables found."

        combined_df = pd.concat(all_tables, ignore_index=True)
        combined_df.to_excel(RAW_FILE, index=False)

        upload_to_gcs(RAW_FILE, RAW_FILE)
        process_and_clean_data()
        return "All records processed, cleaned, and uploaded to GCP!"

    except Exception as e:
        return f"Error: {e}"
    finally:
        driver.quit()

# GCP Upload
def upload_to_gcs(source_file, destination_blob):
    storage_client = storage.Client.from_service_account_json(GCP_CREDENTIALS_PATH)
    bucket = storage_client.bucket(GCP_BUCKET_NAME)
    blob = bucket.blob(destination_blob)
    blob.upload_from_filename(source_file)
    print(f"Uploaded to GCP: {destination_blob}")

# Data transformation
def process_and_clean_data():
    storage_client = storage.Client.from_service_account_json(GCP_CREDENTIALS_PATH)
    bucket = storage_client.bucket(GCP_BUCKET_NAME)
    blob = bucket.blob(RAW_FILE)

    data = blob.download_as_bytes()
    df = pd.read_excel(io.BytesIO(data))

    print("Data fetched successfully!")

    if "Comments" not in df.columns:
        df["Comments"] = None

    df.iloc[:, 0] = df.iloc[:, 0].astype(str)
    cleaned_data = []
    last_valid_row = None

    for index, row in df.iterrows():
        seq_number = row.iloc[0]
        if seq_number.isdigit():
            last_valid_row = row.copy()
            cleaned_data.append(last_valid_row)
        else:
            if last_valid_row is not None:
                last_valid_row = last_valid_row.copy()
                last_valid_row["Comments"] = str(row.iloc[0])
                cleaned_data[-1] = last_valid_row

    df_cleaned = pd.DataFrame(cleaned_data)
    df_cleaned["Comments"] = df_cleaned["Comments"].replace(["nan", pd.NA, None, float("nan")], "Not Assigned").fillna("Not Assigned")
    df_cleaned["Comments"] = df_cleaned["Comments"].str.replace(r"\[\d+(\.\d+)?\]\s*", "", regex=True)
    df_cleaned.reset_index(drop=True, inplace=True)

    df_cleaned.to_excel(CLEANED_FILE, index=False)
    upload_to_gcs(CLEANED_FILE, CLEANED_FILE)
    print(f"Cleaned data uploaded as {CLEANED_FILE}")

# Routes
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/process", methods=["POST"])
def process():
    data = request.json
    html_url = data.get("html_url")

    if not html_url:
        return jsonify({"error": "No URL provided"}), 400

    result = process_html_file(html_url)
    return jsonify({"message": result})

if __name__ == "__main__":
    app.run(debug=True)
