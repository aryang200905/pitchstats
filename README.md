# PitchStats

A soccer analytics web app built on Transfermarkt data for CS564.

- **Database:** MySQL 8.0, schema `pitchstats` (12 tables, 2 views, 5 stored procedures)
- **Backend:** Python + Flask REST API (`mysql-connector-python`, `flask-cors`)
- **Frontend:** React (Create React App) with 4 tabs — Players/Clubs, Compare, Graph, Edit

The database holds **1.8M+ appearance rows** loaded from the CSVs in `data/`.

> **Note on data:** the `data/` folder is **not** tracked in git — the CSVs are
> large (some exceed GitHub's 100 MB limit) and are input data, not source.
> Download the Transfermarkt dataset (Kaggle: *"Football Data from Transfermarkt"*)
> and place the CSVs in `data/` before running the loader.

---

## Project structure

```
project/
├── data/                 # source Transfermarkt CSVs
├── backend/
│   ├── db.py             # shared MySQL connection config
│   ├── app.py            # Flask API (10 query endpoints + 5 procedure endpoints)
│   └── sql/
│       ├── schema.sql    # 12-table schema (drops & recreates the DB)
│       ├── load_data.py  # ETL: cleans CSVs and loads all tables
│       ├── views.sql     # 2 views
│       └── procedures.sql# 5 stored procedures
├── frontend/             # React app (src/App.js is the main UI)
├── docs/                 # checkpoint PDFs
└── README.md
```

---

## Prerequisites

- **MySQL 8.0** running locally. On this machine it is the official server at
  `/usr/local/mysql`, listening on the Unix socket `/tmp/mysql.sock` (TCP 3306 is
  disabled), with root password `pitchstats`.
- **Python 3.11** with `mysql-connector-python` and `flask-cors`:
  ```bash
  pip install mysql-connector-python flask-cors flask
  ```
- **Node.js 20 / npm 10** for the frontend.

> Connection settings live in `backend/db.py`. If your MySQL uses a TCP host/port
> or a different password, edit `DB_CONFIG` there.

---

## 1. Set up the database (one time)

Run from the project root. This drops and recreates `pitchstats`, then loads the data.

```bash
# create the 12 tables
/usr/local/mysql/bin/mysql -u root -ppitchstats --socket=/tmp/mysql.sock < backend/sql/schema.sql

# load all CSVs (takes ~40s; prints row counts per table)
python backend/sql/load_data.py

# create the 2 views and 5 stored procedures
/usr/local/mysql/bin/mysql -u root -ppitchstats --socket=/tmp/mysql.sock < backend/sql/views.sql
/usr/local/mysql/bin/mysql -u root -ppitchstats --socket=/tmp/mysql.sock < backend/sql/procedures.sql
```

Row counts after loading:

| Table                | Rows       |
|----------------------|-----------:|
| Country              | 124        |
| Competition          | 65         |
| Stadium              | 2,987      |
| Club                 | 796        |
| ClubCompetition      | 1,978      |
| Player               | 50,149     |
| Game                 | 72,602     |
| **Appearance**       | **1,813,296** |
| GameEvent            | 1,037,138  |
| PlayerValuation      | 507,815    |
| Transfer             | 35,139     |
| PlayerSeasonStats    | 2,390      |

---

## 2. Run the backend

```bash
cd backend
python app.py
```

Flask serves at **http://127.0.0.1:5001**. Health check: `GET /api/health`.

- Queries: `POST /api/query/<name>` with body `{"params": [...]}`
- Procedures: `POST /api/proc/<name>` with body `{"params": [...]}`

Every endpoint returns `[columnNames, ...rows]`. Stored-procedure validation
errors (e.g. "Player ID does not exist") return HTTP 400 with `{"error": "..."}`.

## 3. Run the frontend

In a second terminal:

```bash
cd frontend
npm install      # first time only
npm start
```

The UI opens at **http://localhost:3000**. `package.json` sets a `proxy` to the
Flask server, so the React app calls `/api/...` directly.

---

## Tab → endpoint map

**Players/Clubs**

| UI operation                                | Endpoint |
|---------------------------------------------|----------|
| Search Players                              | `query/q1_search_players` |
| Club Performance by Competition             | `query/q4_club_performance` |
| Top Scorers by Season                       | `query/q5_top_scorers` |
| Most Valuable Players by Age Group          | `query/q9_most_valuable_by_age` |
| Best Goal Contribution per 90 Minutes       | `query/q10_best_contribution_per90` |
| Get Player Career Summary                   | `proc/sp3_career_summary` |
| Get Top Performers by Position              | `proc/sp5_top_performers` |

**Compare**

| UI operation                | Endpoint |
|-----------------------------|----------|
| Head-to-Head Comparison     | `query/q3_head_to_head` |
| Position Comparison         | `query/q7_position_comparison` |
| Career Club History         | `query/q8_career_club_history` |

**Graph** (rendered as bar chart + table)

| UI operation        | Endpoint |
|---------------------|----------|
| Market Value Trend  | `query/q2_market_value_trend` |
| Transfer Activity   | `query/q6_transfer_activity` |

**Edit** (write operations)

| UI operation             | Endpoint |
|--------------------------|----------|
| Add Player Performance   | `proc/sp1_add_performance` |
| Update Player Valuation  | `proc/sp2_update_valuation` |
| Transfer Player          | `proc/sp4_transfer_player` |

---

## Notes on data-quality fixes

- **Duplicate competition names** in `competitions.csv` violate the `UNIQUE(name)`
  constraint; the loader disambiguates collisions by appending the competition id.
- **National-team club ids** appear in `games.csv` but not `clubs.csv`; games
  referencing an unknown club are filtered out to preserve foreign-key integrity.
- **Q10** (best goal contribution per 90) originally had a `SUM(...) >= 900`
  condition in its `WHERE` clause, which is invalid; it is applied in `HAVING`.
- **SP3** (`GetPlayerCareerSummary`) originally joined `Appearance` with
  `PlayerValuation` in one aggregate, which fanned out and inflated the goal/assist
  sums; the valuation aggregate is now computed separately.
