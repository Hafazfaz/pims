# PIMS - Project Information Management System

## Getting Started

Follow these steps to set up and run the PIMS application locally.

### 1. Environment Setup

It is recommended to use a virtual environment for managing project dependencies.

```bash
# Assuming you have uv installed
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt # Assuming a requirements.txt will be generated or exists
```

### 2. Database Migrations

Apply the necessary database migrations to set up your database schema.

```bash
python pims_datamanagement/manage.py makemigrations
python pims_datamanagement/manage.py migrate
```

### 3. Load Initial Data (Fixtures)

To populate your database with initial data (e.g., roles, default users, test data), load the provided fixtures.

```bash
python pims_datamanagement/manage.py loaddata pims_datamanagement/fixtures/initial_data.json
```

### 4. Create a Superuser

Create an administrator account to access the Django admin panel.

```bash
python pims_datamanagement/manage.py createsuperuser
```

Follow the prompts to set up your superuser credentials.

### 5. Run the Development Server

Start the Django development server to access the application in your browser.

```bash
python pims_datamanagement/manage.py runserver
```

The application should now be accessible at `http://127.0.0.1:8000/`.

## Further Development

This section can be expanded with details on:
*   Running tests
*   Code style guidelines
*   Deployment instructions
*   Project structure overview
