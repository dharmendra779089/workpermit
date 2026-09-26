"""
Comprehensive Automated Test Runner for Opmaint CMMS PTW.
Executes all functional, security, state machine, and edge case tests against the live API.
"""

import urllib.request
import urllib.error
import json
import sys
from datetime import datetime, timedelta

BASE_URL = "https://web-production-5b49a5.up.railway.app"

results = []

def log_test(test_id, category, description, passed, details=""):
    status_str = "PASS" if passed else "FAIL"
    print(f"[{status_str}] {test_id}: {description}")
    if details:
        print(f"       Details: {details}")
    results.append({
        "id": test_id,
        "category": category,
        "description": description,
        "passed": passed,
        "status": status_str,
        "details": details
    })

def make_request(path, method="GET", data=None, token=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8")
            return resp.status, json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        content = e.read().decode("utf-8")
        try:
            return e.code, json.loads(content)
        except:
            return e.code, {"error": content}
    except Exception as e:
        return 500, {"error": str(e)}

def run_tests():
    print(f"=== Starting Comprehensive PTW Test Suite against {BASE_URL} ===")
    
    # -------------------------------------------------------------
    # 1. AUTHENTICATION & ROLE TOKENS
    # -------------------------------------------------------------
    tokens = {}
    users = [
        ("requester@opmaint.com", "REQUESTER", "TC-AUTH-01"),
        ("areaowner@opmaint.com", "AREA_OWNER", "TC-AUTH-02"),
        ("safety@opmaint.com", "SAFETY_OFFICER", "TC-AUTH-03"),
        ("admin@opmaint.com", "ADMIN", "TC-AUTH-04"),
    ]
    
    for email, role, tid in users:
        status, res = make_request("/api/auth/login/", method="POST", data={
            "username": email,
            "password": "SafetyFirst@2026"
        })
        passed = (status == 200 and "access" in res and res.get("user", {}).get("role") == role)
        tokens[role] = res.get("access")
        log_test(tid, "Authentication", f"Login as {role} ({email})", passed, f"Status: {status}, User ID: {res.get('user', {}).get('id')}")

    # Edge Case: Invalid Password
    status, res = make_request("/api/auth/login/", method="POST", data={
        "username": "requester@opmaint.com",
        "password": "WrongPassword!123"
    })
    log_test("TC-AUTH-05", "Authentication", "Reject invalid credentials", status == 401, f"Status: {status}")

    # -------------------------------------------------------------
    # 2. MASTER DATA & SCHEMA REGISTRY
    # -------------------------------------------------------------
    status, types = make_request("/api/permit-types/")
    has_5_types = len(types) >= 5
    excavation_present = any(t['code'] == 'EXCAVATION' for t in types)
    log_test("TC-SCHEMA-01", "Schema Extensibility", "Fetch 5 permit types including Excavation", has_5_types and excavation_present, f"Total Types: {len(types)}")

    cs_type = next((t for t in types if t['code'] == 'CONFINED_SPACE'), {})
    has_entry_log = any(f.get('name') == 'entry_exit_log' for f in cs_type.get('fields', []))
    log_test("TC-SCHEMA-02", "Schema Extensibility", "Confined Space contains mandatory Entry/Exit Log field", has_entry_log, "Entry/Exit Log field verified")

    status, date_filtered = make_request("/api/permits/?start_date=2026-01-01&end_date=2026-12-31", token=tokens["REQUESTER"])
    log_test("TC-FILTER-01", "Permits Filtering", "Filter permits by date range (start_date, end_date)", status == 200, f"Returned: {len(date_filtered)} permits")

    status, plants = make_request("/api/plants/", token=tokens["ADMIN"])
    log_test("TC-MASTER-01", "Master Data", "Fetch industrial plants list", status == 200 and len(plants) >= 2, f"Plants count: {len(plants)}")

    status, areas = make_request("/api/areas/", token=tokens["ADMIN"])
    log_test("TC-MASTER-02", "Master Data", "Fetch process areas list", status == 200 and len(areas) >= 4, f"Areas count: {len(areas)}")

    status, equipment = make_request("/api/equipment/", token=tokens["ADMIN"])
    log_test("TC-MASTER-03", "Master Data", "Fetch equipment assets list", status == 200 and len(equipment) >= 7, f"Equipment count: {len(equipment)}")

    status, stats = make_request("/api/dashboard/stats/", token=tokens["REQUESTER"])
    log_test("TC-DASH-01", "Dashboard KPIs", "Fetch real-time KPI statistics", status == 200 and "active_count" in stats, f"Active: {stats.get('active_count')}, Expiring: {stats.get('expiring_soon_count')}")

    # -------------------------------------------------------------
    # 3. EXTENSIBLE SCHEMA & SAFETY VALIDATION EDGE CASES
    # -------------------------------------------------------------
    # Edge Case: Hot Work with combustible gas LEL >= 10% (CRITICAL SAFETY RULE)
    now = datetime.utcnow()
    eq1_id = equipment[0]['id']
    dangerous_permit = {
        "permit_type": "HOT_WORK",
        "title": "Dangerous Welding Attempt with High LEL",
        "description": "Attempting welding with dangerous gas level",
        "contractor_name": "Test Contractor",
        "team_size": 2,
        "equipment": eq1_id,
        "planned_start": (now + timedelta(hours=1)).isoformat() + "Z",
        "planned_end": (now + timedelta(hours=8)).isoformat() + "Z",
        "hazards": ["Open flame / Sparks"],
        "ppe_required": ["Welding shield / Cutting goggles"],
        "precautions": ["All combustible materials cleared within 10 metres radius"],
        "type_data": {
            "hot_work_type": "Welding",
            "fire_watch_assigned": "Test Watch",
            "fire_extinguisher_type": "DCP (Dry Chemical Powder) 9kg",
            "combustibles_cleared_radius_m": 10,
            "gas_test_o2_pct": 20.9,
            "gas_test_lel_pct": 14.5, # DANGEROUS! >= 10%
            "gas_test_time": (now + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M")
        },
        "submit_immediately": True
    }
    status, res = make_request("/api/permits/", method="POST", data=dangerous_permit, token=tokens["REQUESTER"])
    is_rejected = (status == 400 and ("gas_test_lel_pct" in str(res) or "SAFETY VIOLATION" in str(res)))
    log_test("TC-SAFETY-01", "Safety Edge Case", "Reject Hot Work with dangerous LEL >= 10%", is_rejected, f"Status: {status}, Error: {res}")

    # Edge Case: Planned End before Planned Start
    invalid_time_permit = dict(dangerous_permit)
    invalid_time_permit["type_data"]["gas_test_lel_pct"] = 0.0
    invalid_time_permit["planned_start"] = (now + timedelta(hours=8)).isoformat() + "Z"
    invalid_time_permit["planned_end"] = (now + timedelta(hours=2)).isoformat() + "Z"
    status, res = make_request("/api/permits/", method="POST", data=invalid_time_permit, token=tokens["REQUESTER"])
    log_test("TC-SAFETY-02", "Safety Edge Case", "Reject permit with planned_end <= planned_start", status == 400, f"Status: {status}, Error: {res}")

    # -------------------------------------------------------------
    # 4. FULL STATE MACHINE LIFECYCLE WALKTHROUGH
    # -------------------------------------------------------------
    # 4.1 Create DRAFT (Hot Work)
    valid_hot_work = {
        "permit_type": "HOT_WORK",
        "title": "Comprehensive Test Hot Work Permit",
        "description": "Automated verification of full lifecycle state machine",
        "contractor_name": "Verified Quality Contractors Ltd",
        "team_size": 3,
        "equipment": eq1_id,
        "planned_start": (now - timedelta(minutes=1)).isoformat() + "Z", # ready for immediate activation
        "planned_end": (now + timedelta(hours=6)).isoformat() + "Z",
        "hazards": ["Open flame / Sparks", "Flammable vapours or gases"],
        "ppe_required": ["Welding shield / Cutting goggles", "Leather welding apron & gloves"],
        "precautions": ["All combustible materials cleared within 10 metres radius", "Fire watch person assigned and present"],
        "type_data": {
            "hot_work_type": "Welding",
            "fire_watch_assigned": "S. Rajesh Kumar",
            "fire_extinguisher_type": "CO2 4.5kg",
            "combustibles_cleared_radius_m": 12,
            "gas_test_o2_pct": 20.9,
            "gas_test_lel_pct": 0.0,
            "gas_test_time": now.strftime("%Y-%m-%dT%H:%M")
        },
        "submit_immediately": False
    }
    status, created_permit = make_request("/api/permits/", method="POST", data=valid_hot_work, token=tokens["REQUESTER"])
    permit_id = created_permit.get("id")
    p_num = created_permit.get("permit_number")
    log_test("TC-STATE-01", "State Machine", f"Create DRAFT permit ({p_num})", status == 201 and created_permit.get("status") == "DRAFT", f"ID: {permit_id}")

    # 4.2 Submit DRAFT -> PENDING_APPROVAL
    status, submitted_permit = make_request(f"/api/permits/{permit_id}/submit/", method="POST", token=tokens["REQUESTER"])
    log_test("TC-STATE-02", "State Machine", f"Submit permit DRAFT -> PENDING_APPROVAL", status == 200 and submitted_permit.get("status") == "PENDING_APPROVAL", f"Status: {submitted_permit.get('status')}")

    # 4.3 CRITICAL RULE: Self-Approval Prevention
    status, res = make_request(f"/api/permits/{permit_id}/approve/", method="POST", data={"comment": "Self-approval attempt"}, token=tokens["REQUESTER"])
    log_test("TC-RULE-01", "Permission Rule", "Block person from approving their own permit", status == 403, f"Status: {status}, Response: {res}")

    # 4.4 Premature Activation Check (Before All Approvals)
    status, res = make_request(f"/api/permits/{permit_id}/activate/", method="POST", token=tokens["REQUESTER"])
    log_test("TC-RULE-02", "Permission Rule", "Block activation when approvals are missing", status == 400, f"Status: {status}, Response: {res}")

    # 4.4b Work Logging Invariant: Work cannot be logged against a permit that is not ACTIVE
    status, unauth_work = make_request(f"/api/permits/{permit_id}/log_work/", method="POST", data={
        "task_description": "Attempting to log work before activation"
    }, token=tokens["REQUESTER"])
    log_test("TC-RULE-05", "Safety Rule", "Block logging work against permit that is not ACTIVE", status == 400, f"Status: {status}")

    # 4.5 Area Owner Approves
    status, ao_approved = make_request(f"/api/permits/{permit_id}/approve/", method="POST", data={
        "comment": "Area Owner verified line isolation and fire watch.",
        "signature_data": "data:image/svg+xml;utf8,<svg>test_signature_ao</svg>"
    }, token=tokens["AREA_OWNER"])
    log_test("TC-STATE-03", "State Machine", "Area Owner signs and approves permit", status == 200, f"Approvals count: {len(ao_approved.get('approvals', []))}")

    # 4.6 Safety Officer Approves -> Transitions to APPROVED
    status, fully_approved = make_request(f"/api/permits/{permit_id}/approve/", method="POST", data={
        "comment": "Safety Officer atmospheric tests confirmed zero LEL.",
        "signature_data": "data:image/svg+xml;utf8,<svg>test_signature_so</svg>"
    }, token=tokens["SAFETY_OFFICER"])
    is_fully_approved = (status == 200 and fully_approved.get("status") == "APPROVED")
    log_test("TC-STATE-04", "State Machine", "Multi-party approval transitions status to APPROVED", is_fully_approved, f"Final Status: {fully_approved.get('status')}")

    # 4.7 Activate Permit -> ACTIVE
    status, active_permit = make_request(f"/api/permits/{permit_id}/activate/", method="POST", token=tokens["REQUESTER"])
    is_active = (status == 200 and active_permit.get("status") == "ACTIVE")
    log_test("TC-STATE-05", "State Machine", "Activate permit APPROVED -> ACTIVE", is_active, f"Actual Start: {active_permit.get('actual_start')}")

    # 4.7b Work Logging on ACTIVE permit succeeds
    status, work_res = make_request(f"/api/permits/{permit_id}/log_work/", method="POST", data={
        "worker_name": "Suresh Pillai",
        "hours_spent": 2.5,
        "task_description": "Root pass welding and radiographic inspection alignment completed."
    }, token=tokens["REQUESTER"])
    has_work_log = (status == 200 and len(work_res.get("work_logs", [])) > 0)
    log_test("TC-WORK-01", "Work Logging", "Log technician labor hours against ACTIVE permit", has_work_log, f"Work logs count: {len(work_res.get('work_logs', []))}")

    # 4.8 Emergency Suspension by Safety Officer
    status, suspended_permit = make_request(f"/api/permits/{permit_id}/suspend/", method="POST", data={
        "reason": "Sudden localized thunderstorm with lightning strike risk on column."
    }, token=tokens["SAFETY_OFFICER"])
    is_suspended = (status == 200 and suspended_permit.get("status") == "SUSPENDED")
    log_test("TC-STATE-06", "State Machine", "Safety Officer initiates EMERGENCY SUSPENSION", is_suspended, f"Status: {suspended_permit.get('status')}")

    # 4.9 Unauthorized Resumption Attempt (Requester cannot resume)
    status, res = make_request(f"/api/permits/{permit_id}/resume/", method="POST", data={"notes": "Trying to resume"}, token=tokens["REQUESTER"])
    log_test("TC-RULE-03", "Permission Rule", "Block Requester from resuming suspended permit", status == 403, f"Status: {status}")

    # 4.10 Resumption by Safety Officer
    status, resumed_permit = make_request(f"/api/permits/{permit_id}/resume/", method="POST", data={
        "notes": "Weather cleared. Column grounded and inspected. Work safe to resume."
    }, token=tokens["SAFETY_OFFICER"])
    is_resumed = (status == 200 and resumed_permit.get("status") == "ACTIVE")
    log_test("TC-STATE-07", "State Machine", "Safety Officer authorizes RESUMPTION -> ACTIVE", is_resumed, f"Status: {resumed_permit.get('status')}")

    # 4.11 Extension Request Flow
    status, ext_permit = make_request(f"/api/permits/{permit_id}/request_extension/", method="POST", data={
        "hours": 3,
        "reason": "Additional gusset plate alignment required."
    }, token=tokens["REQUESTER"])
    log_test("TC-STATE-08", "Extension Flow", "Requester submits extension request (+3h)", status == 200 and ext_permit.get("extension_status") == "REQUESTED", f"Ext Status: {ext_permit.get('extension_status')}")

    # Safety Officer Approves Extension
    status, ext_approved = make_request(f"/api/permits/{permit_id}/approve_extension/", method="POST", data={
        "approved": True,
        "comment": "Extension approved for second shift."
    }, token=tokens["SAFETY_OFFICER"])
    log_test("TC-STATE-09", "Extension Flow", "Safety Officer approves extension request", status == 200 and ext_approved.get("extension_status") == "APPROVED", f"New Planned End: {ext_approved.get('planned_end')}")

    # 4.12 Work Completion by Requester -> CLOSED
    status, closed_permit = make_request(f"/api/permits/{permit_id}/close/", method="POST", data={
        "completion_notes": "Weld bead completed and visual dye penetrant inspection passed. Area swept."
    }, token=tokens["REQUESTER"])
    is_closed = (status == 200 and closed_permit.get("status") == "CLOSED")
    log_test("TC-STATE-10", "State Machine", "Requester marks work complete -> CLOSED", is_closed, f"Closed At: {closed_permit.get('closed_at')}")

    # 4.13 Safety Officer Final Verification -> CLOSED_VERIFIED
    status, verified_permit = make_request(f"/api/permits/{permit_id}/verify_closure/", method="POST", data={
        "notes": "Physical plant walk-around completed. Fire blankets removed, fire extinguisher returned, housekeeping certified clean."
    }, token=tokens["SAFETY_OFFICER"])
    is_verified = (status == 200 and verified_permit.get("status") == "CLOSED_VERIFIED")
    log_test("TC-STATE-11", "State Machine", "Safety Officer verifies closure -> CLOSED_VERIFIED", is_verified, f"Verified By: {verified_permit.get('closure_verified_by_name')}")

    # 4.14 Terminal State Re-open Attempt (Must be rejected)
    status, res = make_request(f"/api/permits/{permit_id}/activate/", method="POST", token=tokens["REQUESTER"])
    log_test("TC-RULE-04", "Safety Rule", "Block activation of terminal CLOSED_VERIFIED permit", status == 400, f"Status: {status}")

    # -------------------------------------------------------------
    # 5. REJECTION WORKFLOW
    # -------------------------------------------------------------
    status, p_reject = make_request("/api/permits/", method="POST", data={
        "permit_type": "HEIGHT",
        "title": "Roof Painting with Defective Ladder",
        "description": "Painting gutter line",
        "contractor_name": "Test Painter",
        "team_size": 2,
        "equipment": eq1_id,
        "planned_start": (now + timedelta(hours=1)).isoformat() + "Z",
        "planned_end": (now + timedelta(hours=4)).isoformat() + "Z",
        "hazards": ["Fall from elevation"],
        "ppe_required": ["Full body safety harness with double shock-absorbing lanyards"],
        "precautions": ["100% tie-off policy strictly enforced at all times"],
        "type_data": {
            "height_in_metres": 8.0,
            "access_method": "Secured Industrial Extension Ladder",
            "fall_arrest_equipment": "Harness",
            "anchor_point_checked": True,
            "anchor_point_location": "Beam",
            "barricading_below": True
        },
        "submit_immediately": True
    }, token=tokens["REQUESTER"])
    reject_id = p_reject.get("id")

    # Reject without reason (Must Fail)
    status, res = make_request(f"/api/permits/{reject_id}/reject/", method="POST", data={"reason": ""}, token=tokens["SAFETY_OFFICER"])
    log_test("TC-REJECT-01", "Rejection Rule", "Block rejection without mandatory reason", status == 400, f"Status: {status}")

    # Reject with valid reason
    status, rejected_permit = make_request(f"/api/permits/{reject_id}/reject/", method="POST", data={
        "reason": "Uncertified ladder specified for 8m work. Scaffolding or MEWP mandatory."
    }, token=tokens["SAFETY_OFFICER"])
    log_test("TC-REJECT-02", "Rejection Rule", "Reject permit with documented reason -> REJECTED", status == 200 and rejected_permit.get("status") == "REJECTED", f"Status: {rejected_permit.get('status')}")

    # -------------------------------------------------------------
    # 6. SPATIAL CONFLICT DETECTION ENGINE
    # -------------------------------------------------------------
    status, conflict_res = make_request("/api/permits/pre_check_conflicts/", method="POST", data={
        "equipment_id": eq1_id,
        "planned_start": (now + timedelta(hours=1)).isoformat() + "Z",
        "planned_end": (now + timedelta(hours=6)).isoformat() + "Z",
        "permit_type": "HOT_WORK"
    }, token=tokens["REQUESTER"])
    has_conflicts = "conflicts" in conflict_res
    log_test("TC-CONFLICT-01", "Conflict Engine", "Pre-check spatial and temporal conflicts API", status == 200 and has_conflicts, f"Conflicts checked: {len(conflict_res.get('conflicts', []))}")

    # -------------------------------------------------------------
    # 7. IMMUTABLE AUDIT TRAIL VERIFICATION
    # -------------------------------------------------------------
    status, full_detail = make_request(f"/api/permits/{permit_id}/", token=tokens["REQUESTER"])
    audit_logs = full_detail.get("audit_logs", [])
    has_full_trail = len(audit_logs) >= 6 # CREATED, SUBMITTED, APPROVED, ACTIVATED, SUSPENDED, RESUMED, CLOSED, VERIFIED
    log_test("TC-AUDIT-01", "Audit Trail", "Verify complete immutable audit trail generation", has_full_trail, f"Log entries: {len(audit_logs)}")

    # -------------------------------------------------------------
    # SUMMARY
    # -------------------------------------------------------------
    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])
    failed_count = total - passed_count
    print(f"\n=== Test Suite Complete: {passed_count}/{total} PASSED, {failed_count} FAILED ===")
    
    with open("test_results.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    run_tests()
