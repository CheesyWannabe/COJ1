# CSV Judge — Online CSV Comparison System

A full-stack web app where you upload a **reference CSV** (ground truth), then submit
other CSV files to be automatically scored 0–100 against it.

---

## File Map — All 15 Files

```
csv-judge/
│
├── README.md                        ← You are here
│
├── backend/
│   ├── main.py                      ← FastAPI server — 4 REST endpoints
│   ├── judge.py                     ← Core comparison engine (scoring algorithm)
│   └── requirements.txt             ← Python dependencies
│
├── frontend/
│   ├── index.html                   ← HTML shell that loads the React app
│   ├── package.json                 ← Node dependencies (React, Vite)
│   ├── vite.config.js               ← Vite bundler config + dev proxy to backend
│   ├── nginx.conf                   ← Nginx config used inside Docker
│   ├── Dockerfile.frontend          ← Builds and serves the React app via nginx
│   └── src/
│       ├── main.jsx                 ← React entry point (mounts <App />)
│       ├── App.jsx                  ← Full UI — upload, results, leaderboard, config tabs
│       └── index.css                ← All styles
│
├── tests/
│   └── test_judge.py                ← 16 pytest test cases for the judge engine
│
└── docker/
    ├── Dockerfile.backend           ← Builds the Python/FastAPI backend image
    └── docker-compose.yml           ← Runs frontend + backend together with one command
```

---

## What Each File Does

### `backend/main.py`
The FastAPI web server. Exposes four endpoints:

| Method   | Path                  | What it does                                      |
|----------|-----------------------|---------------------------------------------------|
| `POST`   | `/upload-reference`   | Receives a CSV and stores it as the ground truth  |
| `POST`   | `/submit`             | Receives a CSV, scores it, returns JSON result    |
| `GET`    | `/results`            | Returns all past submission scores for a session  |
| `DELETE` | `/results`            | Clears submission history for a session           |

Sessions are isolated with an `X-Session-Id` header (auto-generated on first request).

### `backend/judge.py`
The scoring engine. Given a reference CSV and a submission CSV it:
1. **Aligns columns** — matches headers by name similarity (Levenshtein), so `"Score"` matches `"score"`, `"city_name"` matches `"cityName"`, etc.
2. **Builds a cost matrix** — every ref-row vs every sub-row is scored for similarity.
3. **Assigns rows optimally** — uses the **Hungarian algorithm** (`scipy`) for ≤500 rows, greedy matching for larger files.
4. **Scores each cell** — exact match = 1.0, numeric within tolerance = 1.0, string similarity = partial score.
5. **Calculates final score** — weighted average across all cells, penalising missing/extra rows.

### `backend/requirements.txt`
Python packages: `fastapi`, `uvicorn`, `pandas`, `numpy`, `scipy`, `python-multipart`.

### `frontend/src/App.jsx`
The entire React UI. Four tabs:
- **Upload & Compare** — drag-and-drop reference + submission, runs comparison, shows score ring + diff table
- **Results** — history of all submissions, sortable by score or time
- **Leaderboard** — top 20 scores ranked with medal badges
- **Config** — toggles for case sensitivity, numeric tolerance, extra-row penalty, etc.

### `frontend/src/index.css`
All visual styles — upload zones, score ring, diff table highlighting (green/yellow/red cells), badges, leaderboard rows.

### `frontend/src/main.jsx`
Two lines — imports React and mounts `<App />` into `index.html`'s `#root` div.

### `frontend/index.html`
Bare HTML shell. Just a `<div id="root">` and a `<script>` tag that loads `main.jsx`.

### `frontend/package.json`
Declares `react`, `react-dom`, and `vite` as dependencies. Defines `npm run dev` and `npm run build`.

### `frontend/vite.config.js`
Configures Vite to proxy `/upload-reference`, `/submit`, `/results` to `localhost:8000` during local development so the frontend and backend can run on different ports without CORS issues.

### `frontend/nginx.conf`
Nginx server block used inside the Docker frontend container. Serves the built React files and proxies `/api/` requests to the backend service.

### `frontend/Dockerfile.frontend`
Two-stage Docker build: Stage 1 uses Node to `npm run build`, Stage 2 copies the `dist/` folder into an nginx image.

### `docker/Dockerfile.backend`
Installs Python dependencies and starts `uvicorn main:app` on port 8000.

### `docker/docker-compose.yml`
Defines two services (`backend` on port 8000, `frontend` on port 3000) and wires them together. One command starts everything.

### `tests/test_judge.py`
16 pytest tests covering every scoring scenario — see "Running the Tests" below.

---

## How to Run

### Option 1 — Docker (easiest, recommended)

Requires: [Docker Desktop](https://www.docker.com/products/docker-desktop/)

```bash
# From the csv-judge/ root folder:
cd docker
docker-compose up --build
```

- **Frontend** → http://localhost:3000
- **Backend API docs** → http://localhost:8000/docs

To stop: `Ctrl+C`, then `docker-compose down`

---

### Option 2 — Local development (two terminals)

Requires: Python 3.10+, Node.js 18+

**Terminal 1 — Backend**

```bash
cd csv-judge/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

**Terminal 2 — Frontend**

```bash
cd csv-judge/frontend
npm install
npm run dev
```

You should see:
```
  VITE v5.x  ready in 300ms
  ➜  Local:   http://localhost:5173/
```

Open **http://localhost:5173** in your browser.

> The Vite dev server automatically proxies API calls to port 8000 — no CORS setup needed.

---

### Option 3 — Backend only (API / curl testing)

```bash
cd csv-judge/backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Open the auto-generated Swagger UI at **http://localhost:8000/docs**.

```bash
# 1. Upload reference
curl -X POST http://localhost:8000/upload-reference \
  -F "file=@my_reference.csv" \
  -H "X-Session-Id: test-session-1"

# 2. Submit and score
curl -X POST http://localhost:8000/submit \
  -F "file=@my_submission.csv" \
  -F "label=alice" \
  -H "X-Session-Id: test-session-1"

# 3. View all results
curl http://localhost:8000/results \
  -H "X-Session-Id: test-session-1"
```

---

## Running the Tests

```bash
cd csv-judge
pip install pytest
pytest tests/test_judge.py -v
```

Expected output:
```
test_perfect_match                PASSED   score = 100
test_completely_different         PASSED   score ≈ 0
test_partial_match                PASSED   50 < score < 100
test_column_order_shuffled        PASSED   score = 100
test_row_order_shuffled           PASSED   score = 100
test_missing_rows                 PASSED   missing_rows = 2
test_extra_rows_penalised         PASSED   penalised < unpenalised
test_case_insensitive             PASSED   score = 100
test_case_sensitive               PASSED   score < 100
test_numeric_tolerance            PASSED   score = 100
test_numeric_no_tolerance         PASSED   score < 100
test_whitespace_trimming          PASSED   score = 100
test_empty_cells                  PASSED   score = 100
test_duplicate_rows               PASSED   score = 100
test_similar_column_names         PASSED   score = 100
test_column_weights               PASSED   name-heavy > balanced
test_single_row                   PASSED   score = 100
test_missing_column_in_submission PASSED   column not found
16 passed
```

---

## Scoring Formula

```
cell_score(ref, sub)  =  1.0   if exact match (after normalisation)
                         1.0   if numeric and |ref - sub| / ref ≤ tolerance
                         0.5   if numeric and within 10× tolerance
                         sim   if string similarity ≥ threshold  (Levenshtein)
                         0.0   otherwise

row_score(i)  =  Σ (cell_score × col_weight)  /  Σ col_weights

final_score   =  Σ row_score(i)  /  denominator  ×  100

denominator   =  n_ref_rows  +  (extra_sub_rows  if  penalize_extra  else  0)

result        =  clamp(final_score, 0, 100)  rounded to 2 decimal places
```

---

## Grading Scale

| Score   | Grade |
|---------|-------|
| 95–100  | S     |
| 85–94   | A     |
| 70–84   | B     |
| 55–69   | C     |
| 35–54   | D     |
| 0–34    | F     |
