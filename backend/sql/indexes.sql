-- PitchStats performance indexes (Checkpoint 4).
--
-- Run ONCE, AFTER load_data.py has populated the tables. Building indexes on an
-- already-loaded table is faster than maintaining them during the 1.8M-row bulk
-- load, and it mirrors how the CP4 before/after measurements were taken.
--
-- The four indexes back the queries benchmarked in CP4:
--   idx_player_name          -> player name lookups (search-by-name, SP3 career summary)
--   idx_club_name            -> club name lookups (Q4 club performance dashboard)
--   idx_player_position_dob  -> multi-condition player search (Q1: position + date_of_birth)
--   idx_game_season          -> season-filtered queries (Q5 top scorers, Q10 contribution/90)

USE pitchstats;

CREATE INDEX idx_player_name         ON Player(name);
CREATE INDEX idx_club_name           ON Club(name);
CREATE INDEX idx_player_position_dob ON Player(position, date_of_birth);
CREATE INDEX idx_game_season         ON Game(season);
