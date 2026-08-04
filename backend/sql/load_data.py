"""Load and clean the Transfermarkt CSVs into the pitchstats database.

Run from anywhere:  python3 backend/sql/load_data.py

Loading order respects foreign keys. Rows that would violate referential
integrity (e.g. games referencing national teams that aren't in clubs.csv)
are filtered out. Two tables are *derived* rather than loaded 1:1:
  - Stadium: de-duplicated from stadium names in clubs.csv + games.csv
  - ClubCompetition: derived from each club's domestic competition plus the
    competitions it actually appeared in (via games). placement left NULL.
"""
import csv
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db import get_connection  # noqa: E402

# Allow very large CSV fields (some description/url columns are big)
csv.field_size_limit(10 * 1024 * 1024)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
BATCH = 5000


def path(name):
    return os.path.join(DATA_DIR, name)


def clean(v):
    """Empty string -> None."""
    if v is None:
        return None
    v = v.strip()
    return v if v != "" else None


def to_int(v):
    v = clean(v)
    if v is None:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def to_date(v):
    """Return YYYY-MM-DD from values like '1978-06-09 00:00:00' or None."""
    v = clean(v)
    if v is None:
        return None
    return v.split(" ")[0][:10]


def reader(name):
    f = open(path(name), newline="", encoding="utf-8")
    return f, csv.DictReader(f)


def executemany(cur, sql, rows):
    """Insert in batches, returning number of rows sent."""
    total = 0
    for i in range(0, len(rows), BATCH):
        cur.executemany(sql, rows[i:i + BATCH])
        total += len(rows[i:i + BATCH])
    return total


def stream_insert(cur, conn, name, sql, build_row):
    """Stream a large CSV, inserting in batches. build_row returns a tuple or None."""
    f, rd = reader(name)
    batch, sent = [], 0
    for row in rd:
        t = build_row(row)
        if t is not None:
            batch.append(t)
        if len(batch) >= BATCH:
            cur.executemany(sql, batch)
            sent += len(batch)
            conn.commit()
            batch = []
    if batch:
        cur.executemany(sql, batch)
        sent += len(batch)
        conn.commit()
    f.close()
    return sent


def main():
    t0 = time.time()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SET FOREIGN_KEY_CHECKS=0")  # we enforce integrity by filtering
    cur.execute("SET UNIQUE_CHECKS=0")
    counts = {}

    # ---- Country ---------------------------------------------------------
    f, rd = reader("countries.csv")
    rows, country_ids, country_name_to_id = [], set(), {}
    for r in rd:
        cid = to_int(r["country_id"])
        nm = clean(r["country_name"])
        if cid is None or nm is None or cid in country_ids:
            continue
        country_ids.add(cid)
        country_name_to_id.setdefault(nm, cid)
        rows.append((cid, nm, clean(r["confederation"])))
    f.close()
    executemany(cur, "INSERT IGNORE INTO Country (country_id,name,confederation) VALUES (%s,%s,%s)", rows)
    conn.commit()
    counts["Country"] = len(rows)

    # ---- Competition -----------------------------------------------------
    f, rd = reader("competitions.csv")
    rows, comp_ids, comp_to_country, used_names = [], set(), {}, set()
    for r in rd:
        cid = clean(r["competition_id"])
        nm = clean(r["name"])
        typ = clean(r["type"]) or "unknown"
        if cid is None or nm is None or cid in comp_ids:
            continue
        # name is UNIQUE in the schema; disambiguate collisions
        if nm in used_names:
            nm = f"{nm} ({cid})"
        used_names.add(nm)
        comp_ids.add(cid)
        ctry = to_int(r["country_id"])
        if ctry in country_ids:
            comp_to_country[cid] = ctry
        rows.append((cid, nm, typ))
    f.close()
    executemany(cur, "INSERT IGNORE INTO Competition (competition_id,name,type) VALUES (%s,%s,%s)", rows)
    conn.commit()
    counts["Competition"] = len(rows)

    # ---- Stadium (derived) ----------------------------------------------
    # de-dup names from clubs.csv (has capacity) and games.csv (no capacity)
    stadium_cap = {}
    f, rd = reader("clubs.csv")
    for r in rd:
        nm = clean(r["stadium_name"])
        if nm:
            cap = to_int(r["stadium_seats"])
            if nm not in stadium_cap or (cap and not stadium_cap[nm]):
                stadium_cap[nm] = cap
    f.close()
    f, rd = reader("games.csv")
    for r in rd:
        nm = clean(r["stadium"])
        if nm and nm not in stadium_cap:
            stadium_cap[nm] = None
    f.close()
    rows = [(nm, cap) for nm, cap in stadium_cap.items()]
    executemany(cur, "INSERT INTO Stadium (name,capacity) VALUES (%s,%s)", rows)
    conn.commit()
    counts["Stadium"] = len(rows)
    # build name -> stadium_id map
    cur.execute("SELECT stadium_id, name FROM Stadium")
    stadium_name_to_id = {nm: sid for sid, nm in cur.fetchall()}

    # ---- Club ------------------------------------------------------------
    f, rd = reader("clubs.csv")
    rows, club_ids = [], set()
    club_domestic_comp = {}  # club_id -> competition_id (for ClubCompetition)
    for r in rd:
        cid = to_int(r["club_id"])
        nm = clean(r["name"])
        if cid is None or nm is None or cid in club_ids:
            continue
        club_ids.add(cid)
        sid = stadium_name_to_id.get(clean(r["stadium_name"]))
        dom = clean(r["domestic_competition_id"])
        country = comp_to_country.get(dom)
        if dom in comp_ids:
            club_domestic_comp[cid] = dom
        rows.append((cid, nm, None, to_int(r["squad_size"]), sid, country))
    f.close()
    executemany(cur,
                "INSERT IGNORE INTO Club (club_id,name,type,squad_size,stadium_id,country_id) VALUES (%s,%s,%s,%s,%s,%s)",
                rows)
    conn.commit()
    counts["Club"] = len(rows)

    # ---- Player ----------------------------------------------------------
    f, rd = reader("players.csv")
    rows, player_ids, player_name_to_id = [], set(), {}
    for r in rd:
        pid = to_int(r["player_id"])
        nm = clean(r["name"])
        if pid is None or nm is None or pid in player_ids:
            continue
        player_ids.add(pid)
        player_name_to_id.setdefault(nm, pid)
        country = country_name_to_id.get(clean(r["country_of_citizenship"]))
        cur_club = to_int(r["current_club_id"])
        if cur_club not in club_ids:
            cur_club = None
        rows.append((pid, nm, to_date(r["date_of_birth"]), clean(r["position"]),
                     clean(r["sub_position"]), clean(r["foot"]), to_int(r["height_in_cm"]),
                     country, cur_club))
        if len(rows) >= BATCH:
            cur.executemany("INSERT IGNORE INTO Player (player_id,name,date_of_birth,position,sub_position,foot,height,country_id,current_club_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)
            conn.commit()
            rows = []
    if rows:
        cur.executemany("INSERT IGNORE INTO Player (player_id,name,date_of_birth,position,sub_position,foot,height,country_id,current_club_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)
        conn.commit()
    f.close()
    counts["Player"] = len(player_ids)

    # ---- Game ------------------------------------------------------------
    game_ids = set()
    club_comp_pairs = set()  # (club_id, competition_id) for ClubCompetition

    def build_game(r):
        gid = to_int(r["game_id"])
        home = to_int(r["home_club_id"])
        away = to_int(r["away_club_id"])
        comp = clean(r["competition_id"])
        dt = to_date(r["date"])
        if (gid is None or dt is None or home not in club_ids or away not in club_ids
                or home == away or comp not in comp_ids or gid in game_ids):
            return None
        game_ids.add(gid)
        club_comp_pairs.add((home, comp))
        club_comp_pairs.add((away, comp))
        sid = stadium_name_to_id.get(clean(r["stadium"]))
        return (gid, dt, to_int(r["season"]) or 0, clean(r["round"]), home, away,
                to_int(r["home_club_goals"]), to_int(r["away_club_goals"]), comp, sid,
                to_int(r["attendance"]))

    counts["Game"] = stream_insert(cur, conn, "games.csv",
        "INSERT IGNORE INTO Game (game_id,date,season,round,home_club_id,away_club_id,home_score,away_score,competition_id,stadium_id,attendance) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        build_game)

    # ---- ClubCompetition (derived) --------------------------------------
    for cid, comp in club_domestic_comp.items():
        club_comp_pairs.add((cid, comp))
    rows = [(cid, comp, None) for (cid, comp) in club_comp_pairs]
    executemany(cur, "INSERT IGNORE INTO ClubCompetition (club_id,competition_id,placement) VALUES (%s,%s,%s)", rows)
    conn.commit()
    counts["ClubCompetition"] = len(rows)

    # ---- Appearance (large) ---------------------------------------------
    def build_app(r):
        pid = to_int(r["player_id"])
        gid = to_int(r["game_id"])
        cid = to_int(r["player_club_id"])
        if pid not in player_ids or gid not in game_ids or cid not in club_ids:
            return None
        return (pid, gid, cid, to_int(r["minutes_played"]) or 0, to_int(r["goals"]) or 0,
                to_int(r["assists"]) or 0, to_int(r["yellow_cards"]) or 0, to_int(r["red_cards"]) or 0)

    counts["Appearance"] = stream_insert(cur, conn, "appearances.csv",
        "INSERT IGNORE INTO Appearance (player_id,game_id,club_id,minutes_played,goals,assists,yellow_cards,red_cards) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        build_app)

    # ---- GameEvent (large) ----------------------------------------------
    def build_event(r):
        gid = to_int(r["game_id"])
        if gid not in game_ids:
            return None
        pid = to_int(r["player_id"]); pid = pid if pid in player_ids else None
        cid = to_int(r["club_id"]); cid = cid if cid in club_ids else None
        etype = clean(r["type"]) or "Unknown"
        return (gid, pid, cid, etype, to_int(r["minute"]), clean(r["description"]))

    counts["GameEvent"] = stream_insert(cur, conn, "game_events.csv",
        "INSERT INTO GameEvent (game_id,player_id,club_id,event_type,minute,description) VALUES (%s,%s,%s,%s,%s,%s)",
        build_event)

    # ---- PlayerValuation -------------------------------------------------
    def build_val(r):
        pid = to_int(r["player_id"])
        dt = to_date(r["date"])
        if pid not in player_ids or dt is None:
            return None
        cid = to_int(r["current_club_id"]); cid = cid if cid in club_ids else None
        return (pid, dt, to_int(r["market_value_in_eur"]), cid)

    counts["PlayerValuation"] = stream_insert(cur, conn, "player_valuations.csv",
        "INSERT IGNORE INTO PlayerValuation (player_id,date,market_value_eur,current_club_id) VALUES (%s,%s,%s,%s)",
        build_val)

    # ---- Transfer --------------------------------------------------------
    def build_transfer(r):
        pid = to_int(r["player_id"])
        if pid not in player_ids:
            return None
        frm = to_int(r["from_club_id"]); frm = frm if frm in club_ids else None
        to_c = to_int(r["to_club_id"]); to_c = to_c if to_c in club_ids else None
        return (pid, frm, to_c, to_date(r["transfer_date"]),
                to_int(r["transfer_fee"]) or 0, clean(r["transfer_season"]))

    counts["Transfer"] = stream_insert(cur, conn, "transfers.csv",
        "INSERT INTO Transfer (player_id,from_club_id,to_club_id,transfer_date,transfer_fee,season) VALUES (%s,%s,%s,%s,%s,%s)",
        build_transfer)

    # ---- PlayerSeasonStats (FBref secondary dataset, best-effort) --------
    # Map FBref 'Comp' league labels -> Transfermarkt competition_id codes.
    comp_label_map = {
        "Premier League": "GB1", "La Liga": "ES1", "Serie A": "IT1",
        "Bundesliga": "L1", "Ligue 1": "FR1",
    }
    comp_label_map = {k: v for k, v in comp_label_map.items() if v in comp_ids}
    pss_rows, seen_pss = [], set()
    try:
        f, rd = reader("players_data-2025_2026.csv")
        for r in rd:
            name = clean(r.get("Player"))
            pid = player_name_to_id.get(name)
            comp_label = clean(r.get("Comp"))
            comp = None
            if comp_label:
                for lbl, code in comp_label_map.items():
                    if lbl.lower() in comp_label.lower():
                        comp = code
                        break
            if pid is None or comp is None:
                continue
            key = (pid, comp, 2025)
            if key in seen_pss:
                continue
            seen_pss.add(key)
            pss_rows.append((pid, comp, 2025, to_int(r.get("MP")) or 0, to_int(r.get("Starts")) or 0,
                             to_int(r.get("Min")) or 0, to_int(r.get("Gls")) or 0, to_int(r.get("Ast")) or 0,
                             None, 0, 0, 0, 0, 0))
        f.close()
        if pss_rows:
            executemany(cur, "INSERT IGNORE INTO PlayerSeasonStats (player_id,competition_id,season,matches_played,starts,minutes_played,goals,assists,passing_accuracy,progressive_passes,shot_creating_actions,tackles,interceptions,blocks) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", pss_rows)
            conn.commit()
    except FileNotFoundError:
        pass
    counts["PlayerSeasonStats"] = len(pss_rows)

    cur.execute("SET FOREIGN_KEY_CHECKS=1")
    cur.execute("SET UNIQUE_CHECKS=1")
    conn.commit()

    # ---- Report ----------------------------------------------------------
    print("\n===== ROW COUNTS (inserted) =====")
    order = ["Country", "Competition", "Stadium", "Club", "ClubCompetition", "Player",
             "Game", "Appearance", "GameEvent", "PlayerValuation", "Transfer", "PlayerSeasonStats"]
    for t in order:
        print(f"  {t:<20} {counts.get(t, 0):>10,}")
    print("\n===== VERIFYING via COUNT(*) =====")
    for t in order:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"  {t:<20} {cur.fetchone()[0]:>10,}")
    print(f"\nDone in {time.time() - t0:.1f}s")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
