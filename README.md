# Aroga Data Pipeline 🏥🧠

Aroga is a cloud-based data ingestion and processing pipeline that enables healthcare providers to upload medical HTML/CSV data, process it using a Flask backend, store it on Azure Blob Storage, trigger Azure Data Factory (ADF) pipelines, and visualize insights in Power BI.

## 🚀 Project Features

- 📄 Upload and parse HTML/CSV medical claim files.
- 🧼 Extract tables, clean data, and normalize structure.
- ☁️ Upload raw and cleaned files to **Azure Blob Storage**.
- 🧩 Trigger **Azure Data Factory Pipelines** on blob creation.
- 📊 Load data into **Azure SQL** tables (CleanedClaims, CsvUploads, CsvMetadata).
- 📈 Feed cleaned data into **Power BI reports**.
- 👩‍⚕️ User authentication system (signup/login/logout).
- 🌐 Fully deployed on **Render** using Docker.

---

## 🧠 Workflow Overview

![Workflow](./ProjectWorkflow.png)

---

## 💻 Tech Stack

- **Backend:** Flask (Python 3.10)
- **Frontend:** HTML (Jinja templates)
- **Database:** Azure SQL Server
- **Storage:** Azure Blob Storage
- **Data Factory:** Azure Data Factory pipeline with trigger
- **Deployment:** Render (Dockerized app)
- **Auth:** Flask sessions + hashed passwords
- **ORM:** SQLAlchemy

---

## 🧾 File Upload Flow

### HTML File

1. Upload `.html` file via `/upload`
2. Extract all `<table>` sections labeled with "Paid", "In Hold", or "Refused"
3. Merge them into a single DataFrame → `output_combined.xlsx`
4. Clean the data (remove garbage rows, unify headers)
5. Upload cleaned file as `cleaned_output_combined.xlsx` to Azure Blob

### CSV File

1. Upload `.csv` via `/upload_csv`
2. Store in Blob as `csvfile.csv`
3. Auto-generate metadata (`user_id`, `upload_id`, `timestamp`)
4. Upload metadata as `metadatafile.csv` to Azure Blob

---

## 🔁 Azure Data Factory Pipeline

- **Trigger:** Fires on blob creation in the `cleanedfile` container
- **Pipeline:** `ProcessUploaded`
- **Conditions:**
  - File path includes `csv_uploads` → `CopyCsvUploads`
  - File name == `metadatafile.csv` → `CopyMetaData`
  - File name == `cleaned_output_combined.xlsx` → `CopyCleanedClaims`

---

## 🧪 Local Development

```bash
# Clone repo
git clone https://github.com/QInvst/Aroga-Production.git
cd Aroga-Production

# Create virtual env & install dependencies
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate
pip install -r requirements.txt

# Add .env file
AZURE_CONNECTION_STRING=your-connection-string
AZURE_CONTAINER_NAME=cleanedfile
AZURE_SQL_CONN=your-azure-sqlalchemy-uri

# Run locally
python app.py
