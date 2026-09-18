import argparse
import json
import os
import secrets
import string
import time

from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, db, auth, exceptions

load_dotenv()


def get_service_account():
    sa = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if sa:
        return json.loads(sa), credentials.Certificate(json.loads(sa))
    path = os.environ["FIREBASE_SERVICE_ACCOUNT_PATH"]
    return json.loads(open(path).read()), credentials.Certificate(path)


def normalize_mac(mac):
    return "".join(ch for ch in mac if ch.isalnum()).upper()


def main():
    p = argparse.ArgumentParser(description="Create a Firebase Auth account for an ESP8266 device")
    p.add_argument("--school-id", required=True)
    p.add_argument("--mac", required=True, help="MAC address of the ESP8266 (pair code), e.g. A4:CF:12:F2:C3:DD")
    p.add_argument("--class-id", help="If given, permanently links the device to this class")
    p.add_argument("--label", default="Attendor device")
    args = p.parse_args()

    mac = normalize_mac(args.mac)

    sa, cred = get_service_account()
    firebase_admin.initialize_app(
        cred,
        {"databaseURL": os.environ["FIREBASE_DATABASE_URL"], "projectId": sa["project_id"]},
    )

    password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
    email = f"device-{mac.lower()}@attendor.in"
    try:
        device_user = auth.create_user(email=email, password=password)
        auth.set_custom_user_claims(device_user.uid, {"mac": mac})
    except exceptions.EmailAlreadyExistsError:
        print(f"device {mac} already exists; set a new password")
        return

    ref = db.reference(f"schools/{args.school_id}/devices/{mac}")
    ref.set(
        {
            "label": args.label,
            "schoolId": args.school_id,
            "classId": args.class_id or "",
            "authEmail": email,
            "createdAt": int(time.time() * 1000),
        }
    )
    if args.class_id:
        db.reference(f"schools/{args.school_id}/classes/{args.class_id}/deviceId").set(mac)

    print("Device provisioned. Program these into the ESP8266 (firmware/src/secrets.h):")
    print(json.dumps(
        {
            "mac/pairCode": mac,
            "authEmail": email,
            "authPassword": password,
            "classId": args.class_id or "(none yet)",
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()