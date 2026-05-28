# mis_project

Legacy PHP MIS project request system rebuilt as a Django application.

## Local Development Setup

```powershell
py -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py test accounts project_requests
python manage.py runserver
```

## Apps

- **accounts** — Custom user model, department, and department-scoped role helpers.
- **project_requests** — Project request lifecycle (draft → submit → approve → assign → complete).
