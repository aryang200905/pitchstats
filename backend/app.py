"""PitchStats Flask backend.

Exposes one REST endpoint family for the 10 analytical queries and one for the
5 stored procedures. Every response uses the array-of-arrays contract the React
frontend expects: the first element is the list of column names, the remaining
elements are data rows (also arrays), e.g.

    [["Player Name", "Goals"], ["Messi", 443], ...]

Errors return HTTP 400 with {"error": "..."} so the UI can surface the message
raised by a stored procedure (SIGNAL SQLSTATE '45000').
"""
from decimal import Decimal
from datetime import date, datetime

from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector

from db import get_connection

app = Flask(__name__)
CORS(app)


def _jsonify_value(v):
    """Make DB values JSON-friendly (Decimal -> float, date -> ISO string)."""
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def run_query(sql, params=()):
    """Run a SELECT and return [columnNames, row, row, ...]."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        columns = [d[0] for d in cur.description]
        rows = [[_jsonify_value(v) for v in row] for row in cur.fetchall()]
        cur.close()
        return [columns] + rows
    finally:
        conn.close()


def _resolve(value, table, id_col, allow_blank=False):
    """Accept either a numeric id or a name and return the matching id.

    The UI lets the user type a player/club name; this turns that name into the
    id the queries and procedures expect. A purely numeric value is used as-is.
    """
    if value is None or (isinstance(value, str) and value.strip() == ""):
        if allow_blank:
            return None
        raise ValueError(f"Please provide a {table.lower()} name or id")

    text = str(value).strip()
    if text.isdigit():
        return int(text)

    # Strip a trailing "  (#12345)" that the autocomplete adds to its labels.
    if "(#" in text and text.rstrip().endswith(")"):
        inside = text[text.rfind("(#") + 2:-1]
        if inside.isdigit():
            return int(inside)

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT {id_col} FROM {table} "
            f"WHERE name = %s ORDER BY {id_col} LIMIT 1",
            (text,),
        )
        row = cur.fetchone()
        if row is None:
            cur.execute(
                f"SELECT {id_col} FROM {table} "
                f"WHERE name LIKE %s ORDER BY {id_col} LIMIT 1",
                (f"%{text}%",),
            )
            row = cur.fetchone()
        cur.close()
    finally:
        conn.close()

    if row is None:
        raise ValueError(f"No {table.lower()} found matching '{text}'")
    return row[0]


def resolve_player(value, allow_blank=False):
    return _resolve(value, "Player", "player_id", allow_blank)


def resolve_club(value, allow_blank=False):
    return _resolve(value, "Club", "club_id", allow_blank)


# ---------------------------------------------------------------------------
# 10 analytical queries. Each entry: (column labels are taken from SQL aliases,
# builder maps the incoming string params to a typed tuple).
# ---------------------------------------------------------------------------

def q1_search_players(p):
    # params: position1, position2, goal_average, appearance_count
    pos1, pos2, goal_avg, appear = p[0], p[1], p[2], p[3]
    sql = """
        SELECT p.name AS `Player Name`,
               c.name AS `Club Name`,
               p.position AS `Position`,
               ROUND(AVG(a.goals), 3) AS `Average Goals`,
               ROUND(AVG(a.assists), 3) AS `Average Assists`,
               COUNT(a.appearance_id) AS `Games`
        FROM Player p
        JOIN Appearance a ON a.player_id = p.player_id
        JOIN Club c ON c.club_id = p.current_club_id
        WHERE p.position IN (%s, %s)
        GROUP BY p.player_id, p.name, c.name, p.position
        HAVING AVG(a.goals) >= %s AND COUNT(a.appearance_id) >= %s
        ORDER BY AVG(a.goals) DESC
        LIMIT 20
    """
    return run_query(sql, (pos1 or 'Attack', pos2 or 'Midfield',
                           float(goal_avg or 0), int(appear or 0)))


def q4_club_performance(p):
    club_id = resolve_club(p[0])
    sql = """
        SELECT comp.name AS `Competition Name`,
               v.matches AS `Matches`,
               v.wins AS `Wins`,
               v.draws AS `Draws`,
               v.losses AS `Losses`,
               v.goals_for AS `Goals For`,
               v.goals_against AS `Goals Against`
        FROM ClubCompetitionPerformanceView v
        JOIN Competition comp ON comp.competition_id = v.competition_id
        WHERE v.club_id = %s
        ORDER BY v.matches DESC
    """
    return run_query(sql, (club_id,))


def q5_top_scorers(p):
    season = p[0]
    sql = """
        SELECT p.name AS `Player Name`,
               c.name AS `Club Name`,
               COUNT(DISTINCT a.game_id) AS `Games`,
               SUM(a.goals) AS `Total Goals`,
               SUM(a.assists) AS `Assists`,
               ROUND(SUM(a.goals) * 90.0 / NULLIF(SUM(a.minutes_played), 0), 2)
                   AS `Goals Per 90 Minutes`
        FROM Player p
        JOIN Appearance a ON a.player_id = p.player_id
        JOIN Game g ON g.game_id = a.game_id
        JOIN Club c ON c.club_id = p.current_club_id
        WHERE g.season = %s
        GROUP BY p.player_id, p.name, c.name
        HAVING SUM(a.goals) >= 10
        ORDER BY SUM(a.goals) DESC
        LIMIT 15
    """
    return run_query(sql, (int(season or 2024),))


def q9_most_valuable_by_age(p):
    limit = int(p[0] or 5)
    sql = """
        WITH latest_val AS (
            SELECT pv.player_id, pv.market_value_eur, pv.current_club_id,
                   ROW_NUMBER() OVER (PARTITION BY pv.player_id
                                      ORDER BY pv.date DESC) AS rn
            FROM PlayerValuation pv
        )
        SELECT age_range AS `Age Range`,
               name AS `Player Name`,
               club_name AS `Club Name`,
               market_value_eur AS `Market Value Eur`,
               position AS `Position`
        FROM (
            SELECT age_range, name, club_name, market_value_eur, position,
                   ROW_NUMBER() OVER (PARTITION BY age_range
                                      ORDER BY market_value_eur DESC) AS rk
            FROM (
                SELECT
                    CASE
                        WHEN TIMESTAMPDIFF(YEAR, p.date_of_birth, CURDATE())
                             BETWEEN 18 AND 21 THEN '18-21'
                        WHEN TIMESTAMPDIFF(YEAR, p.date_of_birth, CURDATE())
                             BETWEEN 22 AND 25 THEN '22-25'
                        WHEN TIMESTAMPDIFF(YEAR, p.date_of_birth, CURDATE())
                             BETWEEN 26 AND 29 THEN '26-29'
                        ELSE '30+'
                    END AS age_range,
                    p.name, c.name AS club_name,
                    lv.market_value_eur, p.position
                FROM Player p
                JOIN latest_val lv
                     ON lv.player_id = p.player_id AND lv.rn = 1
                LEFT JOIN Club c ON c.club_id = lv.current_club_id
                WHERE p.date_of_birth IS NOT NULL
                  AND lv.market_value_eur IS NOT NULL
            ) base
        ) ranked
        WHERE rk <= %s
        ORDER BY age_range, market_value_eur DESC
    """
    return run_query(sql, (limit,))


def q10_best_contribution_per90(p):
    season = p[0]
    # NOTE: CP3 draft had `AND SUM(a.minutes_played) >= 900` in the WHERE clause,
    # which is invalid SQL. The minutes filter is moved to HAVING below.
    sql = """
        SELECT p.name AS `Player Name`,
               c.name AS `Club Name`,
               SUM(a.goals) AS `Total Goals`,
               SUM(a.assists) AS `Total Assists`,
               ROUND((SUM(a.goals) + SUM(a.assists)) * 90.0
                     / NULLIF(SUM(a.minutes_played), 0), 2)
                   AS `Contribution Per 90 Minutes`
        FROM Player p
        JOIN Appearance a ON a.player_id = p.player_id
        JOIN Game g ON g.game_id = a.game_id
        JOIN Club c ON c.club_id = p.current_club_id
        WHERE g.season = %s
        GROUP BY p.player_id, p.name, c.name
        HAVING SUM(a.minutes_played) >= 900
           AND (SUM(a.goals) + SUM(a.assists)) >= 10
        ORDER BY (SUM(a.goals) + SUM(a.assists)) * 90.0
                 / NULLIF(SUM(a.minutes_played), 0) DESC
        LIMIT 15
    """
    return run_query(sql, (int(season or 2024),))


def q2_market_value_trend(p):
    player_id = resolve_player(p[0])
    sql = """
        SELECT p.name AS `Player Name`,
               pv.date AS `Date`,
               pv.market_value_eur AS `Market Value Eur`,
               LAG(pv.market_value_eur) OVER (PARTITION BY pv.player_id
                                              ORDER BY pv.date)
                   AS `Previous Value`,
               pv.market_value_eur - LAG(pv.market_value_eur)
                   OVER (PARTITION BY pv.player_id ORDER BY pv.date)
                   AS `Change`
        FROM PlayerValuation pv
        JOIN Player p ON p.player_id = pv.player_id
        WHERE pv.player_id = %s
        ORDER BY pv.date
        LIMIT 500
    """
    return run_query(sql, (player_id,))


def q3_head_to_head(p):
    id1, id2 = resolve_player(p[0]), resolve_player(p[1])
    sql = """
        SELECT p.name AS `Player Name`,
               COUNT(DISTINCT a.game_id) AS `Games`,
               SUM(a.goals) AS `Total Goals`,
               SUM(a.assists) AS `Total Assists`,
               SUM(a.minutes_played) AS `Total Minutes`
        FROM Player p
        JOIN Appearance a ON a.player_id = p.player_id
        WHERE p.player_id IN (%s, %s)
        GROUP BY p.player_id, p.name
    """
    return run_query(sql, (id1, id2))


def q6_transfer_activity(p):
    min_fee = int(p[0] or 50000000)
    sql = """
        SELECT p.name AS `Player Name`,
               fc.name AS `From Club`,
               tc.name AS `To Club`,
               t.transfer_fee AS `Transfer Fee`,
               t.transfer_date AS `Transfer Date`
        FROM Transfer t
        JOIN Player p ON p.player_id = t.player_id
        LEFT JOIN Club fc ON fc.club_id = t.from_club_id
        LEFT JOIN Club tc ON tc.club_id = t.to_club_id
        WHERE t.transfer_fee > %s
        ORDER BY t.transfer_fee DESC
        LIMIT 20
    """
    return run_query(sql, (min_fee,))


def q7_position_comparison(p):
    sql = """
        SELECT p.position AS `Position`,
               COUNT(DISTINCT p.player_id) AS `Player Count`,
               ROUND(AVG(a.goals), 3) AS `Avg Goals`,
               ROUND(AVG(a.assists), 3) AS `Avg Assists`,
               ROUND(AVG(a.minutes_played), 1) AS `Avg Minutes`
        FROM Player p
        JOIN Appearance a ON a.player_id = p.player_id
        WHERE p.position IS NOT NULL AND p.position <> ''
        GROUP BY p.position
        HAVING COUNT(DISTINCT p.player_id) >= 50
        ORDER BY AVG(a.goals) DESC
    """
    return run_query(sql)


def q8_career_club_history(p):
    player_id = resolve_player(p[0])
    sql = """
        SELECT p.name AS `Player Name`,
               c.name AS `Club Name`,
               COUNT(DISTINCT a.game_id) AS `Games`,
               SUM(a.goals) AS `Total Goals`,
               SUM(a.assists) AS `Total Assists`
        FROM Player p
        JOIN Appearance a ON a.player_id = p.player_id
        JOIN Club c ON c.club_id = a.club_id
        WHERE p.player_id = %s
        GROUP BY p.player_id, p.name, c.name
        ORDER BY COUNT(DISTINCT a.game_id) DESC
    """
    return run_query(sql, (player_id,))


QUERIES = {
    "q1_search_players": q1_search_players,
    "q2_market_value_trend": q2_market_value_trend,
    "q3_head_to_head": q3_head_to_head,
    "q4_club_performance": q4_club_performance,
    "q5_top_scorers": q5_top_scorers,
    "q6_transfer_activity": q6_transfer_activity,
    "q7_position_comparison": q7_position_comparison,
    "q8_career_club_history": q8_career_club_history,
    "q9_most_valuable_by_age": q9_most_valuable_by_age,
    "q10_best_contribution_per90": q10_best_contribution_per90,
}


@app.route("/api/query/<name>", methods=["POST"])
def query_endpoint(name):
    fn = QUERIES.get(name)
    if fn is None:
        return jsonify({"error": f"Unknown query '{name}'"}), 404
    params = (request.get_json(silent=True) or {}).get("params", [])
    try:
        return jsonify(fn(params))
    except (mysql.connector.Error, ValueError) as e:
        return jsonify({"error": str(e)}), 400


# ---------------------------------------------------------------------------
# 5 stored procedures.
# ---------------------------------------------------------------------------

def call_proc_with_out(name, in_args, out_count):
    """Call a proc that has OUT params; returns the list of OUT values."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        args = list(in_args) + [0] * out_count
        result = cur.callproc(name, args)
        cur.close()
        conn.commit()
        return list(result)
    finally:
        conn.close()


@app.route("/api/proc/sp1_add_performance", methods=["POST"])
def sp1_add_performance():
    p = (request.get_json(silent=True) or {}).get("params", [])
    try:
        args = [resolve_player(p[0]), int(p[1]), resolve_club(p[2]), int(p[3]),
                int(p[4]), int(p[5]), int(p[6]), int(p[7])]
        conn = get_connection()
        cur = conn.cursor()
        cur.callproc("AddPlayerPerformance", args)
        status = "Performance record added successfully"
        for res in cur.stored_results():
            row = res.fetchone()
            if row:
                status = row[0]
        conn.commit()
        cur.close()
        conn.close()
        return jsonify([["Status"], [status]])
    except (mysql.connector.Error, ValueError, IndexError) as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/proc/sp2_update_valuation", methods=["POST"])
def sp2_update_valuation():
    p = (request.get_json(silent=True) or {}).get("params", [])
    try:
        args = [resolve_player(p[0]), p[1], int(p[2]), resolve_club(p[3])]
        conn = get_connection()
        cur = conn.cursor()
        cur.callproc("UpdatePlayerValuation", args)
        status = "Valuation updated"
        for res in cur.stored_results():
            row = res.fetchone()
            if row:
                status = row[0]
        conn.commit()
        cur.close()
        conn.close()
        return jsonify([["Status"], [status]])
    except (mysql.connector.Error, ValueError, IndexError) as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/proc/sp3_career_summary", methods=["POST"])
def sp3_career_summary():
    p = (request.get_json(silent=True) or {}).get("params", [])
    try:
        pid = resolve_player(p[0])
        # OUT params: name, games, goals, assists, minutes, clubs, club, value
        out = call_proc_with_out("GetPlayerCareerSummary", [pid], 8)
        columns = ["Player Name", "Total Games", "Total Goals", "Total Assists",
                   "Total Minutes", "Clubs Count", "Current Club",
                   "Max Market Value Eur"]
        # out[0] is the IN player_id; out[1:] are the 8 OUT values
        row = [_jsonify_value(v) for v in out[1:9]]
        return jsonify([columns, row])
    except (mysql.connector.Error, ValueError, IndexError) as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/proc/sp4_transfer_player", methods=["POST"])
def sp4_transfer_player():
    p = (request.get_json(silent=True) or {}).get("params", [])
    try:
        from_club = resolve_club(p[1], allow_blank=True)
        args = [resolve_player(p[0]), from_club, resolve_club(p[2]),
                p[3], int(p[4]), p[5]]
        conn = get_connection()
        cur = conn.cursor()
        cur.callproc("TransferPlayer", args)
        status = "Player transferred successfully"
        for res in cur.stored_results():
            row = res.fetchone()
            if row:
                status = row[0]
        conn.commit()
        cur.close()
        conn.close()
        return jsonify([["Status"], [status]])
    except (mysql.connector.Error, ValueError, IndexError) as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/proc/sp5_top_performers", methods=["POST"])
def sp5_top_performers():
    p = (request.get_json(silent=True) or {}).get("params", [])
    try:
        position = p[0] or ""
        season = int(p[1] or 2024)
        min_games = int(p[2] or 0)
        limit = int(p[3] or 10)
        conn = get_connection()
        cur = conn.cursor()
        cur.callproc("GetTopPerformersByPosition",
                     [position, season, min_games, limit])
        columns, rows = ["Info"], []
        for res in cur.stored_results():
            columns = [d[0] for d in res.description]
            rows = [[_jsonify_value(v) for v in row] for row in res.fetchall()]
        cur.close()
        conn.close()
        return jsonify([columns] + rows)
    except (mysql.connector.Error, ValueError, IndexError) as e:
        return jsonify({"error": str(e)}), 400


# ---------------------------------------------------------------------------
# Lookup helpers: let the UI search players/clubs by name and resolve the id,
# and serve the fixed option lists (seasons, positions) for dropdowns.
# ---------------------------------------------------------------------------
@app.route("/api/search/players")
def search_players():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify([])
    sql = """
        SELECT p.player_id, p.name, c.name AS club
        FROM Player p
        LEFT JOIN Club c ON c.club_id = p.current_club_id
        WHERE p.name LIKE %s
        ORDER BY (p.name = %s) DESC, p.name
        LIMIT 15
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, (f"%{q}%", q))
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    out = [
        {
            "id": r[0],
            "label": r[1] + (f" — {r[2]}" if r[2] else "") + f"  (#{r[0]})",
        }
        for r in rows
    ]
    return jsonify(out)


@app.route("/api/search/clubs")
def search_clubs():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify([])
    sql = """
        SELECT c.club_id, c.name, co.name AS country
        FROM Club c
        LEFT JOIN Country co ON co.country_id = c.country_id
        WHERE c.name LIKE %s
        ORDER BY (c.name = %s) DESC, c.name
        LIMIT 15
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, (f"%{q}%", q))
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    out = [
        {
            "id": r[0],
            "label": r[1] + (f" — {r[2]}" if r[2] else "") + f"  (#{r[0]})",
        }
        for r in rows
    ]
    return jsonify(out)


@app.route("/api/options")
def options():
    seasons = run_query(
        "SELECT DISTINCT season FROM Game "
        "WHERE season IS NOT NULL ORDER BY season DESC"
    )[1:]
    positions = run_query(
        "SELECT DISTINCT position FROM Player "
        "WHERE position IS NOT NULL AND position <> '' ORDER BY position"
    )[1:]
    return jsonify({
        "seasons": [r[0] for r in seasons],
        "positions": [r[0] for r in positions],
    })


@app.route("/api/health")
def health():
    try:
        run_query("SELECT 1")
        return jsonify({"status": "ok"})
    except mysql.connector.Error as e:
        return jsonify({"status": "error", "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)
