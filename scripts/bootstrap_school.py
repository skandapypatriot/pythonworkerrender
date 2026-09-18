import argparse
import json
import os
import secrets
import string
import time

from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, db, auth

load_dotenv()


def get_service_account():
    sa = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if sa:
        return json.loads(sa), credentials.Certificate(json.loads(sa))
    path = os.environ["FIREBASE_SERVICE_ACCOUNT_PATH"]
    return json.loads(open(path).read()), credentials.Certificate(path)


def main():
    p = argparse.ArgumentParser(description="Bootstrap a school + create its admin account")
    p.add_argument("--school-name", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--timezone", default="Asia/Kolkata")
    p.add_argument("--school-id", default=None)
    args = p.parse_args()

    sa, cred = get_service_account()
    firebase_admin.initialize_app(
        cred,
        {"databaseURL": os.environ["FIREBASE_DATABASE_URL"], "projectId": sa["project_id"]},
    )

    admin_user = auth.create_user(email=args.email, password=args.password)
    uid = admin_user.uid
    sid = args.school_id or f"school-{int(time.time() * 1000)}"

    db.reference(f"schools/{sid}/profile").set(
        {
            "name": args.school_name,
            "timezone": args.timezone,
            "createdAt": int(time.time() * 1000),
        }
    )
    db.reference(f"schools/{sid}/admins/{uid}").set(True)
    db.reference(f"userMeta/{uid}").set(
        {"role": "admin", "schoolId": sid, "classId": ""}
    )

    print("School bootstrapped.")
    print(f"  schoolId : {sid}")
    print(f"  adminUid : {uid}")
    print(f"  admin    : {args.email}")


if __name__ == "__main__":
    main()