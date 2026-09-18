# Attendor Python Worker

FastAPI background worker that processes entrance scans from the
Attendor ESP8266 class devices (Firebase Realtime DB), plus a live
log web UI.

## Roll

- Polls `schools/*/devices/*/scans`
- Writes attendance + entry logs and responds to the device
- Validates student registrations coming through `registrationCodes`
- Forwards device logs to the live view at `/logs`

## Run locally

```
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # fill in service-account path + DB URL
uvicorn app.main:app --reload
```

## Deploy on Render

`render.yaml` defines a free web service. In Render connect this repo,
then set env vars per `.env.example`:

- `FIREBASE_SERVICE_ACCOUNT_PATH` -> path to a JSON copied into the service
- `FIREBASE_SERVICE_ACCOUNT_JSON` -> (optional) the key JSON as a secret's value
- `FIREBASE_DATABASE_URL` -> `https://<project>-default-rtdb.firebaseio.com`
- `SCHOOL_TIMEZONE` / `POLL_INTERVAL_SEC` (optional) -> defaults: `Asia/Kolkata`, `3`