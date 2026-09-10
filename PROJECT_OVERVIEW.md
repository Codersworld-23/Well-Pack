# WellPack - Project Overview & Gap Analysis

This document provides a comprehensive overview of the current WellPack project architecture, explains the underlying technologies (Next.js and FastAPI), and outlines what needs to be done to fully meet the problem statement expectations.

---

## 1. Basics: Next.js and FastAPI

Since you are new to Next.js and FastAPI, here is a simple breakdown of what they are and how they work in this project.

### Next.js (The Frontend)

Next.js is a React framework used for building web applications.

- **What it does:** It creates the user interface (what the user sees in the browser). It handles routing (moving between pages like `/` and `/admin`), rendering HTML, and making requests to the backend.
- **Why it's used here:** Next.js provides a fast, modern, and responsive interface for both regular users (scanning a label via their phone/web browser) and administrators (viewing the dashboard).
- **Key Concepts:**
  - **App Router (`src/app/`):** Next.js uses file-based routing. A file named `page.tsx` inside a folder automatically becomes a web page.
  - **Components (`src/components/`):** Reusable UI parts like buttons, camera interfaces, and dashboard tables.

### FastAPI (The Backend)

FastAPI is a modern Python web framework for building APIs.

- **What it does:** It runs the "server-side" logic. When the Next.js frontend sends an image, FastAPI receives it, processes it through the entire compliance pipeline (OCR, OpenCV, Rule Engine), and sends the result back.
- **Why it's used here:** Python has the best libraries for AI, Vision (OpenCV), and OCR. FastAPI is extremely fast and automatically generates API documentation (which you can see at `http://localhost:8000/docs`).
- **Key Concepts:**
  - **Routers (`app/routers/`):** These define the API endpoints (e.g., `POST /api/scans`).
  - **Services (`app/services/`):** This is where the heavy lifting happens (processing images, connecting to the database, running AI models).

---

## 2. Architecture & How Files Are Connected

The project follows a standard **Client-Server Architecture**. The Next.js frontend runs independently and talks to the FastAPI backend over HTTP.

### Frontend Structure (`frontend/`)

- `src/app/`: Contains the pages of the web app (e.g., the main scanning page, the admin dashboard).
- `src/components/`: UI components.
- `src/lib/`: Helper functions and API calling logic used by the frontend to talk to the backend.

### Backend Structure (`backend/`)

- `app/main.py`: The entry point for the FastAPI server. It wires up the routers and starts the application.
- `app/routers/`: Endpoints that the frontend calls (e.g., `scan.py`, `rules.py`, `analytics.py`).
- `app/services/`: The core business logic.
  - `vision.py`: Handles OpenCV tasks (measuring character height, checking contrast, checking image blur).
  - `ocr.py`: Extracts text and bounding boxes using RapidOCR.
  - `extractor.py`: Parses the OCR text to find the mandatory fields (MRP, Date, Quantity, etc.).
  - `rag.py` & `cache.py`: Handles vector search over Legal Metrology rules and semantic caching of images.
  - `rule_engine.py`: The deterministic brain that decides if a label passes or fails based on the extracted fields and the retrieved rules.
  - `pipeline.py`: Orchestrates all the above services in order when a new scan comes in.
- `app/database.py` & `app/models.py`: Defines the SQLite database connection and the database tables (Scans, Rules, Users).

### How a Scan Works (The Flow)

1. **User Action:** The user takes a photo on the Next.js frontend.
2. **API Call:** The frontend sends the image to the FastAPI backend via `POST /api/scans`.
3. **Backend Processing (`pipeline.py`):**
   - The image is checked for quality (`vision.py`).
   - The cache is checked to see if this product was already scanned (`cache.py`).
   - If not cached, OCR extracts the text (`ocr.py`), and the extractor finds the data points (`extractor.py`).
   - Physical checks (font sizes, contrast) are run (`vision.py`).
   - The relevant Legal Metrology rules are retrieved (`rag.py`).
   - The Rule Engine checks the data against the rules and generates a verdict (`rule_engine.py`).
   - An LLM (if configured) generates a human-readable narrative.
4. **Response:** The backend saves the scan in the database and sends the verdict back to the Next.js frontend, which displays the result to the user.

---

## 3. Gap Analysis: What is Done vs. What Needs to be Done

Based on the **Problem Statement** and **Expected Solution**, the current prototype is highly advanced and covers almost all core requirements. Below is a breakdown of what is currently implemented and what still needs to be built to complete the solution.

### ✅ What is Already Implemented

- **Automated extraction & validation:** OCR + physical OpenCV analysis works.
- **Detecting mandatory declarations:** Checks MRP, Net Quantity, Date, Address, etc.
- **Font size & readability analysis:** Checks mm height against schedules and WCAG contrast.
- **Rule-based compliance checking:** Fully functional deterministic rule engine grounded in the Legal Metrology Rules, 2011.
- **Dashboard & Repository:** Admin portal exists to monitor inspections, view scanned products, and manage rules.
- **User-friendly web app:** A functioning Next.js web application.
- **Role-based user access:** Admin and inspector roles exist.
- **Technical documentation:** High-level architecture documentation is present.

### 🚀 What Needs to be Done More (The Roadmap)

To fully satisfy the expectations of the problem statement, the following features need to be added:

#### 1. PDF & Editable Report Generation

- **Requirement:** *"Generation of digital compliance reports in PDF and editable formats."*
- **Action Required:** Create a new backend service (e.g., using `ReportLab` or `WeasyPrint` in Python) to generate a PDF report of a scan's verdict, extracted data, and cited rules. Add an endpoint to download this, and surface a "Download Report" button on the Next.js frontend.

#### 2. Mobile Application (React Native)

- **Requirement:** *"User-friendly web and/or mobile-based software application."*
- **Action Required:** While the web application uses the device camera perfectly well, building a dedicated mobile app (e.g., using React Native or Expo) that talks to the same FastAPI backend will fulfill the "mobile-based" software requirement more robustly and provide a native experience for enforcement officers.

#### 3. Real-World Image Validation

- **Requirement:** *"Scanning and analyzing images of packaged commodities."*
- **Action Required:** The system currently relies on synthetic labels for its automated testing (`tools/run_pipeline_check.py`). We need to capture photographs of real-world retail packaging, tune the OCR/Vision preprocessing for real-world lighting and curvature, and validate the pipeline against them.

#### 4. Deployment Framework Documentation

- **Requirement:** *"Technical documentation describing software architecture and deployment framework."*
- **Action Required:** Add a specific section or file (e.g., `DEPLOYMENT.md`) explaining how to deploy this stack to production. This should include containerization (Docker/docker-compose instructions), scaling strategies, and cloud infrastructure setup (e.g., using AWS/GCP for the managed tier versions of Postgres, Redis, and Vector stores).

#### 5. Search and Retrieval Refinements

- **Requirement:** *"Search and retrieval facility for previously scanned products and reports."*
- **Action Required:** Ensure the admin dashboard has robust filtering, pagination, and text-search capabilities to easily find historical scans by brand name, date, or compliance status. (Verify the current Next.js implementation and expand if basic).

#### 6. Exporting to Editable Formats (CSV/Excel)

- **Requirement:** *"Export of reports to PDF and editable formats."*
- **Action Required:** In addition to PDF, add functionality on the admin dashboard to export violation summaries and inspection histories into CSV or Excel format for enforcement officials.
