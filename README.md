# Clonos AI - Log Templates

A Flask-based application for processing and extracting industrial log templates using Vision-Language Models (VLM).

## Features
- Upload PDF files for processing.
- Process logs using `HuggingFaceTB/SmolVLM-256M` or similar models.
- Data storage and retrieval via MongoDB.
- Environment-based configuration.

## Setup

1. **Clone the repository**
   ```bash
   git clone <repository_url>
   cd Log_templates
   ```

2. **Create and activate a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**
   Create a `.env` file in the root directory (refer to `app/config.py` for variables):
   ```env
   SECRET_KEY=your_secret_key
   FLASK_DEBUG=True
   UPLOAD_FOLDER=uploads
   TEMP_FOLDER=temp
   MONGO_URI=mongodb://localhost:27017/
   MONGO_DB_NAME=clonos_ai
   VLM_MODEL_ID=HuggingFaceTB/SmolVLM-256M
   ```

5. **Run the application**
   ```bash
   python run.py
   ```
