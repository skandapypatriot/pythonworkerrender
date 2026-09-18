import asyncio
import time
from datetime import datetime

from . import config
from .firebase_init import ref
from .logbus import log
from .school_time import local_now, to_local, window_for


class Processor:
    def __init__(self):
        self._running = False
        self._task = None

    async def run_loop(self):
        self._running = True
        log("info", "processor loop started")
        while self._running:
            try:
                await asyncio.to_thread(self._tick)
            except Exception as exc:
                log("error", f"tick failed: {exc}")
            await asyncio.sleep(config.POLL_INTERVAL)

    def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self.run_loop())
        return self._task

    def stop(self):
        self._running = False

    def _tick(self):
        self._process_pending_registrations()
        schools = ref("schools").get() or {}
        for sid, school in schools.items():
            tz_name = (school.get("profile") or {}).get("timezone") or config.DEFAULT_TIMEZONE
            devices = school.get("devices") or {}
            for did, device in devices.items():
                try:
                    self._process_device(sid, did, device, school, tz_name)
                    self._process_device_logs(sid, did)
                except Exception as exc:
                    log("error", f"device {did} failed: {exc}")

    def _process_pending_registrations(self):
        pending = ref("pendingRegistrations").get() or {}
        for uid, item in pending.items():
            code = item.get("code")
            code_info = ref(f"registrationCodes/{code}").get() if code else None
            if not code_info:
                log("warn", f"registration {uid}: invalid or consumed code '{code}', deleting")
                ref(f"pendingRegistrations/{uid}").delete()
                continue
            sid = code_info["schoolId"]
            cid = code_info["classId"]
            ref(f"schools/{sid}/students/{uid}").set(
                {
                    "name": item.get("name", ""),
                    "email": item.get("email", ""),
                    "classId": cid,
                    "schoolId": sid,
                    "tagUid": "",
                    "createdAt": int(time.time() * 1000),
                }
            )
            ref(f"schools/{sid}/classes/{cid}/students/{uid}").set(True)
            ref(f"userMeta/{uid}").set(
                {"role": "student", "schoolId": sid, "classId": cid}
            )
            ref(f"pendingRegistrations/{uid}").delete()
            ref(f"registrationCodes/{code}").delete()
            log("info", f"student registered: {item.get('name')} -> class {cid}")

    def _process_device(self, sid, did, device, school, tz_name):
        cid = device.get("classId")
        scans = ref(f"schools/{sid}/devices/{did}/scans").get() or {}
        if not scans:
            return
        cursor = ref(f"_meta/processedScans/{did}").get() or ""
        pending_keys = sorted(k for k in scans if k > cursor)
        if not pending_keys:
            return
        class_node = (school.get("classes") or {}).get(cid) if cid else None
        for scan_id in pending_keys:
            try:
                self._process_scan(sid, did, cid, class_node, scan_id, scans[scan_id], school, tz_name)
            except Exception as exc:
                log("error", f"scan {scan_id} failed: {exc}")
        ref(f"_meta/processedScans/{did}").set(pending_keys[-1])

    def _process_device_logs(self, sid, did):
        logs_ref = ref(f"schools/{sid}/devices/{did}/logs")
        logs = logs_ref.get() or {}
        for key, entry in logs.items():
            level = str(entry.get("level", "info")).lower()
            if level not in ("info", "warn", "error"):
                level = "info"
            log(level, f"[device {did}] {entry.get('message', '')}")
        if logs:
            logs_ref.delete()

    def _process_scan(self, sid, did, cid, class_node, scan_id, scan, school, tz_name):
        tag = scan.get("tagUid")
        now_ms = int(time.time() * 1000)
        ts = scan.get("ts") or now_ms
        if not isinstance(ts, (int, float)) or ts < 1_577_836_800_000 or ts > now_ms + 86_400_000:
            # Device clock not NTP-synced (uptime millis) or absurd: use server time.
            ts = now_ms
        if not class_node:
            self._respond(sid, did, scan_id, False, "Device not assigned to a class")
            return
        if scan.get("type") == "enroll":
            self._handle_enroll(sid, did, cid, class_node, scan_id, tag, ts, tz_name, school)
        else:
            self._handle_attend(sid, did, cid, class_node, scan_id, tag, ts, tz_name, school)

    def _respond(self, sid, did, scan_id, ok, message, **extra):
        payload = {"ok": ok, "message": message, "ts": int(time.time() * 1000), **extra}
        ref(f"schools/{sid}/devices/{did}/responses/{scan_id}").set(payload)
        log("info", f"respond {scan_id}: ok={ok} {message}")

    def _handle_enroll(self, sid, did, cid, class_node, scan_id, tag, ts, tz_name, school):
        command = ref(f"schools/{sid}/devices/{did}/enrollCommand").get()
        if not command:
            self._respond(sid, did, scan_id, False, "No pending card assignment")
            return
        student_uid = command.get("studentUid")
        expires = command.get("expiresAt") or 0
        if time.time() * 1000 > expires:
            ref(f"schools/{sid}/devices/{did}/enrollCommand").delete()
            self._respond(sid, did, scan_id, False, "Card assignment expired")
            return
        members = (class_node.get("students") or {})
        if student_uid not in members:
            self._respond(sid, did, scan_id, False, "Command target not in this class")
            return
        students = school.get("students") or {}
        for uid, student in students.items():
            if student.get("tagUid") and student["tagUid"] == tag and uid != student_uid:
                ref(f"schools/{sid}/students/{uid}/tagUid").set("")
                log("warn", f"reassigned tag {tag} from {uid} to {student_uid}")
        ref(f"schools/{sid}/students/{student_uid}/tagUid").set(tag)
        ref(f"schools/{sid}/devices/{did}/enrollCommand").delete()
        name = (students.get(student_uid) or {}).get("name", student_uid)
        self._respond(sid, did, scan_id, True, f"Card bound: {name}", studentUid=student_uid)

    def _handle_attend(self, sid, did, cid, class_node, scan_id, tag, ts, tz_name, school):
        students = school.get("students") or {}
        tag_to_uid = {
            s.get("tagUid"): uid for uid, s in students.items() if s.get("tagUid")
        }
        if tag not in tag_to_uid:
            self._respond(sid, did, scan_id, False, "Tag not registered")
            return
        uid = tag_to_uid[tag]
        local = to_local(ts, tz_name)
        active_days = class_node.get("activeDays") or [0, 1, 2, 3, 4, 5]
        window, reason = window_for(local, class_node, active_days)
        if not window:
            self._respond(sid, did, scan_id, False, reason, uid=uid)
            return
        date = local.strftime("%Y-%m-%d")
        sessions = (class_node.get("sessions") or {}).get(date, {})
        session = sessions.get(window, {}) or {}
        if session.get("status") == "closed":
            self._log_entry(sid, cid, date, scan_id, uid, ts, window, "late")
            self._respond(sid, did, scan_id, False, "Session closed", uid=uid, window=window)
            return
        att_block = (school.get("attendance") or {}).get(cid, {}).get(date, {}).get(uid, {})
        window_att = att_block.get(window) or {}
        if "present" in window_att and window_att["present"]:
            ref(f"schools/{sid}/attendance/{cid}/{date}/{uid}/{window}/lastScan").set(ts)
            self._log_entry(sid, cid, date, scan_id, uid, ts, window, "present-again")
            self._respond(sid, did, scan_id, True, "Already present", uid=uid, window=window)
        else:
            ref(f"schools/{sid}/attendance/{cid}/{date}/{uid}/{window}/present").set(True)
            ref(f"schools/{sid}/attendance/{cid}/{date}/{uid}/{window}/firstScan").set(ts)
            ref(f"schools/{sid}/attendance/{cid}/{date}/{uid}/{window}/lastScan").set(ts)
            name = (students.get(uid) or {}).get("name", uid)
            self._log_entry(sid, cid, date, scan_id, uid, ts, window, "present")
            self._respond(sid, did, scan_id, True, f"Present: {name}", uid=uid, window=window)
        self._maybe_auto_close(sid, cid, date, window, class_node, school, local)

    def _log_entry(self, sid, cid, date, scan_id, uid, ts, window, status):
        ref(f"schools/{sid}/entryLogs/{cid}/{date}/{scan_id}").set(
            {"uid": uid, "ts": ts, "window": window, "status": status}
        )

    def _maybe_auto_close(self, sid, cid, date, window, class_node, school, local):
        att = (school.get("attendance") or {}).get(cid, {}).get(date, {}) or {}
        members = (class_node.get("students") or {}).keys()
        present = 0
        for uid in members:
            if (att.get(uid, {}).get(window, {}) or {}).get("present"):
                present += 1
        if present == len(members):
            ref(f"schools/{sid}/classes/{cid}/sessions/{date}/{window}").set(
                {
                    "status": "closed",
                    "closedBy": "auto",
                    "closedAt": int(local.timestamp() * 1000),
                }
            )
            log("info", f"session {cid}/{date}/{window} auto-closed (all {present} present)")


processor = Processor()