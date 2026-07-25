# AI-Powered Alertness & Drowsiness Prevention System

A privacy-first, real-time web application designed to monitor user alertness, detect signs of drowsiness, and actively keep users awake through interactive cognitive and physical challenges. Built using a hybrid Client-Edge architecture, it runs AI computer vision models directly in the user's browser via WebAssembly (WASM), ensuring zero network lag and complete privacy.

---

## 🌟 Key Features

*   **Real-time Eye Aspect Ratio (EAR) Tracking**: Measures eyelid distance to detect microsleeps (threshold dynamically calibrated per user on startup).
*   **Mouth Aspect Ratio (MAR) Yawning Detection**: Identifies early signs of fatigue by tracking lip movement and yawning frequencies.
*   **Head Nodding & Tilt (Pose Estimation)**: Detects sudden nods (pitch drop) or side-to-side head tilt (roll).
*   **Physical Activity & Eye Rubbing Check**: Utilizes hand landmark coordinates to detect when the user is rubbing their eyes.
*   **Progressive Alarm & Alert System**: 
    *   *Level 1 Warning*: Gentle text-to-speech audio reminders.
    *   *Level 2 Critical*: Interactive full-screen alerts accompanied by a synthesized siren alarm.
*   **Active Wake-Up Challenges**: Forcibly interrupts drowsiness with cognitive tasks (Math problems, Memory sequences, Reaction clicks) and physical verification (Smile verification).
*   **Gamified Economy & Streaks**: Earn XP for focus time, maintain daily streaks, and unlock focus achievements.
*   **Interactive Dashboard**: View historical focus data, peak alertness times, and personalized break recommendations based on Pandas data analysis.
*   **Exportable Reports**: Generate professional PDF reports (via ReportLab) and CSV logs detailing all drowsiness incidents and focus timelines.
*   **Password Reset via Email**: Token-based password recovery flow using Flask-Mail (time-limited reset links).
*   **Separate Admin Panel**: Environment-credential-based administrator login (fully independent of the user database) to monitor active users and inspect user dashboards.
*   **Optimized Startup**: The camera stream and the AI runtime warm-up start in parallel, so the live feed appears immediately while detectors initialize in the background — backed by a progressive loading checklist and console timing instrumentation.

---

## 🛠️ Technology Stack

*   **Frontend**: HTML5, Vanilla CSS, Vanilla JavaScript (ES6+), Chart.js
*   **Computer Vision**: MediaPipe Face Mesh WASM, MediaPipe Hands WASM, WebRTC (all inference runs client-side in the browser)
*   **Backend**: Python, Flask, Flask-Login, Flask-SQLAlchemy, Flask-Mail
*   **Database**: SQLite locally (ORM via SQLAlchemy); PostgreSQL-compatible via `DATABASE_URL`
*   **Analytics Engine**: Pandas, NumPy
*   **Report Generation**: ReportLab (PDF), CSV
*   **Deployment**: Gunicorn + Nginx on AWS EC2, with DuckDNS for dynamic DNS

---

## 📐 Architecture Overview

```
                        ┌────────────────────────┐
                        │      User Webcam       │
                        └───────────┬────────────┘
                                    │ WebRTC Stream
                                    v
 ┌──────────────────────────────────────────────────────────────────────┐
 │                         Client Browser (Edge)                        │
 │                                                                      │
 │   ┌───────────────────────┐            ┌─────────────────────────┐   │
 │   │  MediaPipe Face Mesh  ├───────────>│   MediaPipe Hands WASM  │   │
 │   └──────────┬────────────┘            └────────────┬────────────┘   │
 │              │ 478 landmarks                        │ 21 landmarks   │
 │              └───────────────────┬──────────────────┘                │
 │                                  v                                   │
 │                     ┌──────────────────────────┐                     │
 │                     │ Alertness Engine (EAR)   │                     │
 │                     └────────────┬─────────────┘                     │
 │                                  │                                   │
 │       ┌──────────────────────────┼──────────────────────────┐        │
 │       │ Alert Thresholds Passed  │ Normal Monitoring State  │        │
 │       v                          v                          v        │
 │  ┌──────────────┐          ┌──────────────┐          ┌──────────────┐│
 │  │ Audio Siren  │          │   TTS Speech │          │ HUD Updates  ││
 │  └──────────────┘          └──────────────┘          └──────────────┘│
 └──────────────────────────────────┬───────────────────────────────────┘
                                    │ JSON Payload (HTTPS POST)
                                    v
 ┌──────────────────────────────────────────────────────────────────────┐
 │                           Flask Backend                              │
 │                                                                      │
 │   ┌───────────────────────┐            ┌─────────────────────────┐   │
 │   │    Route Controllers  ├───────────>│   Pandas Analytics      │   │
 │   └──────────┬────────────┘            └────────────┬────────────┘   │
 │              v                                      v                │
 │   ┌───────────────────────┐            ┌─────────────────────────┐   │
 │   │   SQLAlchemy Models   │            │   ReportLab PDF Engine  │   │
 │   └──────────┬────────────┘            └─────────────────────────┘   │
 │              v                                                       │
 │      SQLite Database                                                 │
 └──────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Getting Started

### Prerequisites
*   Python 3.8 or higher
*   A modern web browser with webcam access

### Setup and Installation

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/dinu-vishruth/drowiness_detector.git
    cd drowiness_detector
    ```

2.  **Create a Virtual Environment**:
    ```bash
    python -m venv venv
    ```

3.  **Activate the Virtual Environment**:
    *   **Windows**:
        ```powershell
        venv\Scripts\activate
        ```
    *   **macOS / Linux**:
        ```bash
        source venv/bin/activate
        ```

4.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

5.  **Configure Environment Variables**:

    Create a `.env` file in the project root. This file holds all secrets and is
    **git-ignored — never commit it**.
    ```ini
    # Flask
    SECRET_KEY=your-random-secret-key

    # Admin panel (kept out of the user database on purpose)
    ADMIN_USERNAME=your-admin-username
    ADMIN_PASSWORD=your-admin-password

    # Email (password-reset flow) — Gmail requires an App Password
    MAIL_SERVER=smtp.gmail.com
    MAIL_PORT=587
    MAIL_USE_TLS=true
    MAIL_USERNAME=your-email@gmail.com
    MAIL_PASSWORD=your-app-password
    MAIL_DEFAULT_SENDER=your-email@gmail.com

    # Optional: point at PostgreSQL instead of local SQLite
    # DATABASE_URL=postgresql://user:pass@host:5432/dbname
    ```
    Generate a strong `SECRET_KEY` with:
    ```bash
    python -c "import secrets; print(secrets.token_hex(32))"
    ```

6.  **Run the Application**:
    ```bash
    python app.py
    ```

7.  **Access the Application**:
    *   Open your browser and navigate to `http://127.0.0.1` (the dev server listens on port `80` by default; override with the `PORT` env var).
    *   Sign up for a new account, or log in using the default developer credentials:
        *   **Username**: `developer`
        *   **Password**: `developer123`

---

## 🔐 Admin Access

The administrator panel is intentionally **separate from the user login system**:

*   Admin credentials come only from the `ADMIN_USERNAME` / `ADMIN_PASSWORD` environment variables — never from the users database. A normal account (even one named `admin`) can never gain administrator privileges.
*   Credentials are checked with a constant-time comparison, and admin state is tracked via an isolated server-side session flag (independent of Flask-Login).

**Usage**:
*   Sign in at `/admin/login` with the credentials from your `.env`.
*   The panel at `/admin` lists active and registered users and lets you inspect any user's dashboard read-only.
*   Sign out at `/admin/logout` (this clears only the admin flag, leaving any normal user session intact).

---

## 🚀 Production Deployment (AWS EC2)

The app is deployed on AWS EC2 behind **Gunicorn + Nginx**, with **DuckDNS** providing a stable hostname.

*   Serve the WSGI app with Gunicorn, e.g. `gunicorn -w 4 -b 127.0.0.1:8000 app:app`, managed by a systemd service.
*   Put Nginx in front as a reverse proxy (and TLS terminator) forwarding to Gunicorn.
*   Provide a `.env` **directly on the server** — because it is git-ignored, `git pull` will never overwrite it. After changing `.env`, restart the service so `load_dotenv()` re-reads it.
*   Camera access (WebRTC / `getUserMedia`) requires a **secure context**, so serve the site over HTTPS in production.

> **Security note:** Rotate any secret that has ever been committed to git history (admin password, mail password, `SECRET_KEY`). Removing `.env` from tracking stops future leaks but does not scrub past commits.

---

## 📋 How It Works (The Core Math)

*   **Eye Aspect Ratio (EAR)**: Computes the ratio of eye openness. A gentle Level-1 warning fires after ~3 consecutive closed-eye frames; sustained closure (~20 frames, or ~12 if corroborated by a genuine drowsy head nod) is the sole trigger for the critical wake-up challenge. Yawns, tilt, looking-down and eye-rubbing are warning-only signals and never fire the challenge on their own.
*   **Mouth Aspect Ratio (MAR)**: Computes mouth elongation to detect yawns. A value exceeding `0.55` triggers a yawn event.
*   **Head Nodding & Tilt**: Roll is computed using `Math.atan2` between outer eye corners. Pitch is computed via the nose-to-chin ratio compared to the mid-eyes baseline.
*   **Eye Rubbing**: Measures the Euclidean distance between fingertips and eye corners; values below `0.08` trigger an eye-rubbing warning.

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
