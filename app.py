from flask import Flask, request, render_template, jsonify
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
from azure.storage.blob import BlobServiceClient
import io
import os
import re
import time
from dotenv import load_dotenv

app = Flask(__name__)

# .env file setup
load_dotenv()
AZURE_CONNECTION_STRING = os.getenv("AZURE_CONNECTION_STRING")
AZURE_CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME")

RAW_FILE = "output_combined.xlsx"
CLEANED_FILE = "cleaned_output_combined.xlsx"

# Extract all sections by heading name
def extract_all_tables(driver):
    tables_data = []

    WebDriverWait(driver, 15).until(EC.presence_of_all_elements_located((By.TAG_NAME, "table")))
    possible_headers = driver.find_elements(By.XPATH, "//*[contains(text(), 'Records')]")

    for header in possible_headers:
        text = header.text.strip()
        match = re.search(r"(Paid|Refused|In Hold)\s+Records", text, re.IGNORECASE)

        if match:
            record_type = match.group(1).strip().capitalize()

            try:
                table = header.find_element(By.XPATH, "following::table[1]")
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

# Upload to Azure Blob
def upload_to_azure_blob(local_file_path, blob_name):
    try:
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)

        with open(local_file_path, "rb") as data:
            container_client.upload_blob(name=blob_name, data=data, overwrite=True)
            print(f"Uploaded to Azure Blob: {blob_name}")
    except Exception as e:
        print(f"Upload error: {e}")

# Data transformation and upload
def process_and_clean_data():
    try:
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)
        blob_client = container_client.get_blob_client(RAW_FILE)

        download_stream = blob_client.download_blob()
        df = pd.read_excel(io.BytesIO(download_stream.readall()))

        print("Data fetched successfully from Azure!")

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

        # Rename columns to match Azure SQL schema
        df_cleaned.rename(columns={
            "SEQ NUMBER": "SeqNumber",
            "SERVICE DATE": "ServiceDate",
            "PRACTITIONER NUMBER": "PractitionerNumber",
            "PHN": "PHN",
            "FEE ITEM": "FeeItem",
            "SHADOW BILL": "ShadowBill",
            "OUT OF PROVINCE": "OutOfProvince",
            "BILLED": "Billed",
            "ADJUST": "Adjust",
            "PAID": "Paid",
            "Record_Type": "Record_Type",
            "Comments": "Comments"
        }, inplace=True)

        # Clean and convert currency columns to float
        currency_columns = ["Billed", "Adjust", "Paid"]
        for col in currency_columns:
            if col in df_cleaned.columns:
                df_cleaned[col] = (
                    df_cleaned[col]
                    .astype(str)
                    .str.replace(r"[$,]", "", regex=True)
                    .replace("", "0")
                    .astype(float)
                )

        df_cleaned.to_excel(CLEANED_FILE, index=False)
        upload_to_azure_blob(CLEANED_FILE, CLEANED_FILE)
        print(f"Cleaned data uploaded as {CLEANED_FILE}")

    except Exception as e:
        print(f"Error in cleaning process: {e}")


# Main process function
def process_html_file(html_url):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)

    try:
        driver.get(html_url)
        time.sleep(2)

        all_tables = extract_all_tables(driver)
        if not all_tables:
            return "No valid tables found."

        combined_df = pd.concat(all_tables, ignore_index=True)
        combined_df.to_excel(RAW_FILE, index=False)

        upload_to_azure_blob(RAW_FILE, RAW_FILE)
        process_and_clean_data()
        return "All records processed, cleaned, and uploaded to Azure Blob!"

    except Exception as e:
        return f"Error: {e}"
    finally:
        driver.quit()

# Routes
@app.route("/")
def index():
    return render_template(
        "index.html",
        video_url="/static/dynamic.mp4",
        logo_url="/static/logo.jpg"
    )


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
