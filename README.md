# Breathe ESG - Relational Emissions Ingest & Analyst Review Portal

An enterprise-ready, multi-tenant ESG data ingestion and auditing portal designed to streamline Scope 1, 2, and 3 emissions tracking, data normalization, anomaly detection, and auditor review workflows.

## 🚀 Key Features

- **Multi-Tenant Architecture**: Complete data isolation between organizations/clients with distinct user profiles and facility mapping.
- **Relational Ingest Pipelines**:
  - **SAP Fuel Export (Scope 1)**: Ingests direct fuel usage with automated unit normalization (e.g., Liters, Gallons).
  - **Utility Electricity Invoices (Scope 2)**: Processes electricity meters, billing period alignment, and MWh/kWh conversions.
  - **Concur API Sync (Scope 3)**: Pulls business travel activity (flights, hotels, car rentals) and calculates emissions based on travel distance.
- **Data Quality & Anomaly Detection**: Proactively flags records as `SUSPICIOUS` or `REJECTED` when they exceed historical thresholds, fail verification rules, or lack proper entity mapping.
- **Auditor Review Workflow**: Secure review loop where analysts can justify adjustments, request unlocks, and lock records into an immutable audit trail.
- **Interactive Dashboard**: Modern analytics interface visualizing monthly emission trends, scope breakdowns, pipeline logs, and real-time status counts.

---

## 📁 Repository Structure

```
├── backend/                   # Django REST Framework application
│   ├── breathe_esg/           # Project configuration (settings, routes, wsgi)
│   ├── emissions/             # Core emissions logic, models, serialization, and ingestion
│   │   ├── management/        # Django commands (e.g., seeding database)
│   │   ├── ingest.py          # Data normalizers and ingestion pipelines
│   │   ├── models.py          # Multi-tenant schemas
│   │   └── views.py           # REST APIs
│   ├── manage.py
│   └── build.sh               # Production build script for deployment
├── frontend/                  # React + Vite + Tailwind CSS / Vanilla CSS application
│   ├── src/
│   │   ├── App.jsx            # Main dashboard app logic
│   │   └── index.css          # Design system, tokens, and animations
│   ├── package.json
│   └── vite.config.js
├── DECISIONS.md               # Architectural decision logs
├── MODEL.md                   # Relational database schema documentation
├── SOURCES.md                 # Emission factor references and data sources
└── TRADEOFFS.md              # Key design and performance tradeoffs
```

---

## 🛠️ Local Installation & Development

### 1. Prerequisites
- **Python 3.10+**
- **Node.js 18+**

### 2. Backend Setup
Navigate to the `backend` directory and set up the development environment:

```bash
cd backend

# Create and activate a virtual environment
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install required dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Seed standard testing data
python manage.py seed_data

# Start the local development server
python manage.py runserver
```

*The backend server will run at [http://localhost:8000/](http://localhost:8000/).*

### 3. Frontend Setup
In a new terminal, navigate to the `frontend` directory and set up the React client:

```bash
cd frontend

# Install package dependencies
npm install

# Run the frontend dev server
npm run dev
```

*The frontend development server will launch at [http://localhost:5173/](http://localhost:5173/).*

---

## 🧪 Seeding & Test Credentials

When running the application for the first time, click the **Seed Standard Settings** button on the login screen or run `python manage.py seed_data` in the backend. 

Use the following pre-configured user credentials to sign in and explore different role flows:

| Username | Password | Role | Organization |
| :--- | :--- | :--- | :--- |
| `acme_analyst` | `password123` | Analyst | Acme Corporation |
| `acme_auditor` | `password123` | Auditor | Acme Corporation |
| `acme_admin` | `password123` | Administrator | Acme Corporation |
| `beta_analyst` | `password123` | Analyst | Beta Services |

---

## ☁️ Deployment Guide (Live Hosting)

This project is fully configured for deployment using a **Vercel (Frontend)** + **Render (Backend)** split-hosting stack.

### 1. Backend Deployment (Render)
1. Sign up/log in to [Render](https://render.com/).
2. Create a new **Web Service** and connect your GitHub repository.
3. Configure the following fields:
   - **Root Directory**: `backend`
   - **Runtime**: `Python 3`
   - **Build Command**: `./build.sh`
   - **Start Command**: `gunicorn breathe_esg.wsgi:application`
4. Add the following **Environment Variables** in the Render dashboard:
   - `SECRET_KEY`: *Any random secure string*
   - `DEBUG`: `False`
   - `ALLOWED_HOSTS`: *Your Render domain (e.g. `breathe-esg.onrender.com`)*
   - `DATABASE_URL`: *(Optional) PostgreSQL database connection string if using a production DB*

### 2. Frontend Deployment (Vercel)
1. Sign up/log in to [Vercel](https://vercel.com/).
2. Click **Add New** > **Project** and select your GitHub repository.
3. Configure the build settings:
   - **Framework Preset**: `Vite`
   - **Root Directory**: `frontend`
4. Expand the **Environment Variables** section and add:
   - `VITE_API_BASE`: *The URL of your deployed Render backend (e.g. `https://breathe-esg.onrender.com`)*
5. Click **Deploy**. Vercel will automatically build and host the React app.

---

## 📊 Emission Calculation Reference
For detailed references regarding emissions scopes, fuel conversion rates, and global warming potential (GWP) factors, see [SOURCES.md](file:///d:/Breath%20ESG%20assignment/SOURCES.md).

For a breakdown of architectural design choices and schemas, refer to [MODEL.md](file:///d:/Breath%20ESG%20assignment/MODEL.md) and [DECISIONS.md](file:///d:/Breath%20ESG%20assignment/DECISIONS.md).
