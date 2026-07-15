# Project Structure

This is a monorepo with two main components:

## Backend

Location: `backend/`

- Python with FastAPI
- To activate the Python virtual environment:
  ```bash
  cd backend
  source .venv/activate
  ```

## Frontend

Location: `frontend/`

- Client-side code (React/Vite based on package.json and vite.config.ts)

## Checking Installed Packages

To check installed package versions:

```bash
cd backend
source .venv/activate
uv pip freeze | rg <package_name>
```

Example: `uv pip freeze | rg google` shows all Google-related packages.
