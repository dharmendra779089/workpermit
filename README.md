# Opmaint CMMS — Permit to Work (PTW) Module

A high-stakes, safety-critical **Permit to Work (PTW)** module built for **Opmaint CMMS**.

In chemical and industrial plants, a Permit to Work is not a to-do list — it is an authorization document that prevents fatal workplace incidents. When a worker welds near a pipe rack with flammable hydrocarbon residue, enters a confined vessel with oxygen deficiency, or works on a 415V switchgear busbar, a single bypassed safety check can cause an explosion or loss of life. This system models a shared permit entity with dynamic type-specific safety schemas, an immutable audit trail, conflict detection, and strict server-side state machine enforcement.

## 🌐 Live Deployed Application

- **Live URL**: **[https://web-production-5b49a5.up.railway.app](https://web-production-5b49a5.up.railway.app)**
- **Hosting Platform**: Railway (Full-stack Python/Django + Managed PostgreSQL)
- **Status**: Live, seeded, and operational with instant demo role-switching buttons.

---

## 🛠 Tech Stack

- **Frontend**: Semantic HTML5, Custom Vanilla CSS3 (Industrial Slate CMMS Design System + Glove-Friendly High-Contrast Mobile Field Mode), Vanilla JavaScript (ES6+), Fetch API.
- **Backend**: Python 3.11, Django 5.x, Django REST Framework (DRF), SimpleJWT (JWT Authentication), Django ORM.
- **Database**: PostgreSQL (with automatic connection via `DATABASE_URL` / `dj-database-url`, and SQLite fallback for instant zero-dependency local testing).
- **Deployment**: Render-ready (`render.yaml`, `build.sh`, `Procfile`, WhiteNoise static file compression, Gunicorn WSGI server).
- **Version Control**: Git / GitHub.

---

## 🚀 Quick Setup Guide (Runs in < 2 Minutes)

### 1. Clone & Setup Virtual Environment
```bash
git clone <your-repo-url>
cd workpermit

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Migrations & Seed Database
```bash
python manage.py migrate
python manage.py seed_data
```
The seed script will populate **4 users** (one per role), **2 industrial plants**, **4 process areas**, **7 critical equipment items**, and **13 realistic industrial permits** across all 10 state machine statuses and all 5 permit types.

### 4. Start Development Server
```bash
python manage.py runserver 8080
```
Open **[http://127.0.0.1:8080/](http://127.0.0.1:8080/)** in your browser.

---

## 🔑 Demo Login Credentials

For quick evaluation, the top navigation includes a **One-Click Quick Switch Bar** to immediately assume any role without typing. You can also log in manually with the following credentials:

| Role | Username / Email | Password | Scope & Responsibilities |
|---|---|---|---|
| **Requester** | `requester@opmaint.com` | `SafetyFirst@2026` | Contractor Supervisor (Rahul Sharma). Creates drafts, submits permits, closes completed work. Cannot approve any permit. |
| **Area Owner** | `areaowner@opmaint.com` | `SafetyFirst@2026` | Production Owner (Priya Nair). Approves permits for equipment in **assigned area only** (Refining & Boiler units). |
| **Safety Officer** | `safety@opmaint.com` | `SafetyFirst@2026` | Plant HSE Officer (Vikram Singh). Approves any permit, suspends any ACTIVE permit instantly, verifies closure walk-around. |
| **System Admin** | `admin@opmaint.com` | `SafetyFirst@2026` | Full administrative access (Tanzeel Admin). Manages plants, equipment, master data, and override authority. |

---

## 🏗 Data Model & Extensible Permit Type Architecture

> *"A junior developer builds four separate forms with copy-pasted code. Show us you can model a shared permit entity with type-specific fields, so a fifth permit type — say Excavation — can be added without rewriting anything."*

### 1. Shared Core Model (`Permit`)
All permits share common core fields:
- `permit_number` (unique `PTW-YYYY-XXXX`)
- `permit_type` (`HOT_WORK`, `CONFINED_SPACE`, `HEIGHT`, `ELECTRICAL_LOTO`, `EXCAVATION`)
- `title`, `description`
- `requester` (FK User)
- `contractor_name`, `team_size`
- `equipment` (FK Equipment) $\rightarrow$ links to Area and Plant
- `planned_start`, `planned_end`, `actual_start`, `actual_end`
- `status` (State machine status)
- `hazards`, `ppe_required`, `precautions` (Checklists)
- `type_data` (JSONField storing dynamic attributes)

### 2. Extensible Declarative Registry (`permits/schemas.py`)
Each permit type is defined declaratively with:
- Metadata (`name`, `description`, `badge_color`, `icon`)
- Recommended hazards, PPE, and precaution items
- Typed field specifications (`type`, `label`, `required`, `unit`, `options`, `validation`)
- Server-side safety validation rules (e.g. combustible gas LEL $\ge 10\%$ is rejected server-side)

**Proof of Extensibility**: We implemented **Excavation & Trenching** right alongside Hot Work, Confined Space, Working at Height, and Electrical LOTO. Adding any future 6th permit type (e.g. Radiography or Chemical Handling) requires only adding a dictionary entry in `PERMIT_TYPE_REGISTRY` — **zero database migrations and zero frontend UI code rewrites required**.

---

## 🔄 State Machine & Server-Side Safety Invariants

```
DRAFT ──submit──> PENDING_APPROVAL ──all approve──> APPROVED ──activate──> ACTIVE
  │                     │                                              │
  │                 any reject                                     ├── suspend ──> SUSPENDED ──resume──> ACTIVE
  ▼                     ▼                                          │
CANCELLED           REJECTED                                       ├── expires ──> EXPIRED
                                                                   │
                                                                   └── close ──> CLOSED ──verify──> CLOSED_VERIFIED
```

### Invariants Enforced Server-Side (Cannot be bypassed by API calls):
1. **Self-Approval Prevention**: A person can **never approve their own permit**, even if their role would otherwise permit it (tested in `PermitSafetyRulesTestCase`).
2. **Multi-Party Sign-Off**: A permit cannot transition to `ACTIVE` unless **every required approver** (both Area Owner and Safety Officer) has approved.
3. **Start-Time Window**: A permit cannot go `ACTIVE` before its planned start time (`now < planned_start`).
4. **Auto-Expiry**: A permit auto-expires when its validity window passes. An expired permit **can never be reactivated** — a new permit must be raised.
5. **Area Boundary Enforcement**: An Area Owner can only approve permits for equipment within their assigned area.
6. **Work Logging Restriction**: Work and extensions can only be performed against `ACTIVE` permits.

---

## ⭐ Advanced Features ("The Bits That Separate Good From Average")

1. **Expiry Handling that Actually Works**:
   - Live visual countdown timer on active permits (`HH:MM:SS`).
   - "Expiring Soon" alert badge when within 2 hours of planned end.
   - Background validation hook auto-expires permits even when no browser is open.
2. **Extension Request Flow**:
   - Requester can request $+N$ hours (1 to 8 hours) with technical justification before expiry.
   - Requires re-approval by Safety Officer.
3. **Spatial & Temporal Conflict Detection**:
   - Automated conflict engine warns when a Hot Work permit overlaps in time and location with a Confined Space Entry permit (or concurrent hot work on the same asset).
4. **Mobile-First / Shop Floor Field Mode**:
   - One-click toggle for technicians working outdoors in sunlight with gloves on: ultra-high contrast, minimum 56px touch targets, yellow-on-black visibility.
5. **Plant Walk-Around QR Code**:
   - Generates unique QR code for every permit so HSE inspectors can scan with a mobile camera during physical site inspections.
6. **Digital Signature Capture**:
   - HTML5 canvas signature pad allowing touch, mouse, or stylus sign-offs recorded in the immutable audit trail.

---

## 🧪 Safety Test Suite

The test suite validates safety rules and state machine invariants:

```bash
python manage.py test
```

### Test Coverage Highlights:
- `test_person_can_never_approve_their_own_permit` (Safety Officer creating own permit cannot self-approve)
- `test_requester_cannot_approve_any_permit` (Permission denied for technicians)
- `test_area_owner_cannot_approve_other_areas` (Area boundaries strictly enforced)
- `test_cannot_activate_unless_every_required_approver_approved` (Both Area Owner & Safety Officer required)
- `test_cannot_activate_before_planned_start_time` (Early activation rejected)
- `test_auto_expiry_and_cannot_reactivate_expired` (Expired permits terminal state)
- `test_safety_officer_can_suspend_and_resume` (Instant emergency suspension & site clearance)
- `test_rejection_requires_mandatory_reason` (Mandatory rejection audit log)
- `test_hot_work_dangerous_lel_rejected_by_schema` (Gas LEL $\ge 10\%$ safety rule validation)
- `test_conflict_detection_between_hot_work_and_confined_space` (Spatial clash detection)

---

## 📋 Architectural Decisions Where Spec Was Silent

1. **Approval Hierarchy**: Required both the Area Owner (owns the physical equipment) and the Safety Officer (verifies environmental safety) to sign off before a permit can transition from `PENDING_APPROVAL` to `APPROVED`.
2. **Dynamic Schema Validation Strategy**: Stored type-specific parameters in a structured `type_data` JSON field with strict declarative validation schemas in `permits/schemas.py`. This provides flexibility for industrial clients while preserving strict typing and boundary validation.
3. **Audit Trail Immutability**: Implemented `PermitAuditLog` with read-only constraints in Django admin and no delete/update endpoints in DRF, ensuring audit compliance during industrial accident investigations.
4. **QR Code Verification**: Standardized QR code encoding to point to the permit's permanent identifier URL for instant mobile lookup.

---

## 🔮 What We'd Build Next

- **Continuous Gas Sensor IoT Telemetry**: Direct MQTT/Bluetooth integration with wireless 4-gas detectors (e.g. Honeywell BW Max XT) to stream live LEL/O2 readings into active permits and auto-suspend if thresholds breach.
- **Physical Lockbox NFC Integration**: Tying Electrical LOTO permits to smart digital key lockboxes that only release physical padlock keys once the permit status is `ACTIVE`.
- **Shift Handover Signatures**: Dedicated mid-shift handover workflow transferring active permits to incoming shift supervisors.

---

## ⚠️ Knowingly Left Broken / Out-of-Scope Tradeoffs

As per section 7 of the assignment specification:
- **Offline Sync & Service Workers**: Left out of scope to focus on backend state machine rigor.
- **WebSockets / Real-Time Server Push**: Polling and live local countdown tickers were used instead of socket connections.
- **Email/SMS Dispatch**: Built a `NotificationService` stub function that logs outbound alerts rather than integrating third-party SMS/SendGrid providers.

---

## 🤖 AI Usage Disclosure

AI assistance was utilized during this build for:
1. Drafting boilerplate schema definitions for industrial hazards, PPE, and technical parameters across the 5 permit types.
2. Accelerating CSS utility classes for the industrial CMMS dark theme and mobile field mode.
3. Formulating comprehensive test fixtures.

All architectural decisions, state machine invariant logic, permission enforcement, conflict detection algorithms, and API structures were designed and reviewed for safety correctness.
