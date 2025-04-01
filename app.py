from flask import Flask, request, render_template, jsonify
from bs4 import BeautifulSoup
import requests
import pandas as pd
from azure.storage.blob import BlobServiceClient
import io
import os
import re
import uuid
from datetime import datetime
from dotenv import load_dotenv

app = Flask(__name__)

# .env setup
load_dotenv()
AZURE_CONNECTION_STRING = os.getenv("AZURE_CONNECTION_STRING")
AZURE_CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME")

RAW_FILE = "output_combined.xlsx"
CLEANED_FILE = "cleaned_output_combined.xlsx"
CSV_FILE_NAME = "csvfile.csv"
CSV_METADATA_NAME = "metadatafile.csv"

# ✨ Upload to Azure Blob

def upload_to_azure_blob(file_data_or_path, blob_name, is_path=True):
    try:
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)

        if is_path:
            with open(file_data_or_path, "rb") as data:
                container_client.upload_blob(name=blob_name, data=data, overwrite=True)
        else:
            container_client.upload_blob(name=blob_name, data=file_data_or_path, overwrite=True)

        print(f"✅ Uploaded to Azure Blob: {blob_name}")
    except Exception as e:
        print(f"❌ Upload error: {e}")


# ✅ Extract HTML tables using BeautifulSoup
def extract_all_tables(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    tables_data = []

    headers = soup.find_all(string=re.compile(r"(Paid|Refused|In Hold)\s+Records", re.IGNORECASE))

    for header in headers:
        parent = header.find_parent()
        if not parent:
            continue

        match = re.search(r"(Paid|Refused|In Hold)\s+Records", header, re.IGNORECASE)
        if match:
            record_type = match.group(1).capitalize()
            next_table = parent.find_next("table")
            if not next_table:
                continue

            rows = next_table.find_all("tr")
            table_data = []

            for row in rows:
                cols = [td.get_text(strip=True) for td in row.find_all("td")]
                if cols:
                    table_data.append(cols)

            headers_row = [th.get_text(strip=True) for th in next_table.find_all("th")]
            if table_data:
                df = pd.DataFrame(table_data, columns=headers_row)
                df["Record_Type"] = record_type
                tables_data.append(df)

    return tables_data


# ✅ Clean and transform downloaded Excel file from Blob
def process_and_clean_data():
    try:
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)
        blob_client = container_client.get_blob_client(RAW_FILE)

        download_stream = blob_client.download_blob()
        df = pd.read_excel(io.BytesIO(download_stream.readall()))
        print("✅ Data fetched successfully from Azure!")

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
        print(f"✅ Cleaned data uploaded as {CLEANED_FILE}")

    except Exception as e:
        print(f"❌ Error in cleaning process: {e}")


# ✅ Process HTML URL
def process_html_file(html_url):
    try:
        response = requests.get(html_url)
        if response.status_code != 200:
            return f"Failed to fetch HTML content: {response.status_code}"

        all_tables = extract_all_tables(response.text)
        if not all_tables:
            return "No valid tables found."

        combined_df = pd.concat(all_tables, ignore_index=True)
        combined_df.to_excel(RAW_FILE, index=False)

        upload_to_azure_blob(RAW_FILE, RAW_FILE)
        process_and_clean_data()
        return "All records processed, cleaned, and uploaded to Azure Blob!"

    except Exception as e:
        return f"Error: {e}"


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file or not file.filename.endswith(".html"):
        return jsonify({"message": "Please upload a valid HTML file"}), 400

    try:
        html_content = file.read().decode("utf-8")
        all_tables = extract_all_tables(html_content)
        if not all_tables:
            return jsonify({"message": "No valid tables found."})

        combined_df = pd.concat(all_tables, ignore_index=True)
        combined_df.to_excel(RAW_FILE, index=False)

        upload_to_azure_blob(RAW_FILE, RAW_FILE)
        process_and_clean_data()

        return jsonify({"message": "HTML file processed and uploaded to Azure!"})
    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500


@app.route("/upload_csv", methods=["POST"])
def upload_csv():
    file = request.files.get("file")
    label = request.form.get("label", "No Label")
    user_id = request.form.get("user_id", "anonymous")

    if not file or not file.filename.endswith(".csv"):
        return jsonify({"message": "Please upload a valid CSV file"}), 400

    try:
        # Always overwrite the single CSV and metadata files
        upload_to_azure_blob(file.read(), CSV_FILE_NAME, is_path=False)

        metadata_df = pd.DataFrame([{
            "upload_id": str(uuid.uuid4()),
            "user_id": user_id,
            "filename": file.filename,
            "label": label,
            "uploaded_at": datetime.utcnow().isoformat(),
            "source_type": "csv"
        }])

        metadata_buffer = io.StringIO()
        metadata_df.to_csv(metadata_buffer, index=False)
        upload_to_azure_blob(metadata_buffer.getvalue(), CSV_METADATA_NAME, is_path=False)

        return jsonify({"message": "CSV and metadata uploaded (overwritten)."})

    except Exception as e:
        return jsonify({"message": f"Error uploading CSV: {str(e)}"}), 500


@app.route("/")
def index():
    return render_template("index.html", video_url="/static/dynamic.mp4", logo_url="/static/logo.jpg")


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