import firebase_admin
from firebase_admin import credentials, db

from . import config


_app = None


def init_firebase():
    global _app
    if _app is None:
        cred = credentials.Certificate(config.SERVICE_ACCOUNT_JSON)
        _app = firebase_admin.initialize_app(
            cred,
            {
                "databaseURL": config.DATABASE_URL,
                "projectId": config.SERVICE_ACCOUNT_JSON.get("project_id"),
            },
        )
    return _app


def ref(path):
    return db.reference(path, app=_app)