-- PitchStats stored procedures (from Checkpoint 3)
USE pitchstats;

DROP PROCEDURE IF EXISTS AddPlayerPerformance;
DROP PROCEDURE IF EXISTS UpdatePlayerValuation;
DROP PROCEDURE IF EXISTS GetPlayerCareerSummary;
DROP PROCEDURE IF EXISTS TransferPlayer;
DROP PROCEDURE IF EXISTS GetTopPerformersByPosition;

DELIMITER //

-- Stored Procedure 1: Add Player Performance Record
CREATE PROCEDURE AddPlayerPerformance(
    IN p_player_id INT,
    IN p_game_id INT,
    IN p_club_id INT,
    IN p_minutes_played INT,
    IN p_goals INT,
    IN p_assists INT,
    IN p_yellow_cards INT,
    IN p_red_cards INT
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;
    START TRANSACTION;

    IF NOT EXISTS (SELECT 1 FROM Player WHERE player_id = p_player_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Player ID does not exist';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM Game WHERE game_id = p_game_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Game ID does not exist';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM Club WHERE club_id = p_club_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Club ID does not exist';
    END IF;

    IF EXISTS (SELECT 1 FROM Appearance WHERE player_id = p_player_id AND game_id = p_game_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'This player already has an appearance record for this game';
    END IF;

    INSERT INTO Appearance (
        player_id, game_id, club_id, minutes_played,
        goals, assists, yellow_cards, red_cards
    ) VALUES (
        p_player_id, p_game_id, p_club_id, p_minutes_played,
        p_goals, p_assists, p_yellow_cards, p_red_cards
    );

    COMMIT;
    SELECT 'Performance record added successfully' AS status;
END//

-- Stored Procedure 2: Update Player Market Value
CREATE PROCEDURE UpdatePlayerValuation(
    IN p_player_id INT,
    IN p_valuation_date DATE,
    IN p_market_value BIGINT,
    IN p_club_id INT
)
BEGIN
    DECLARE existing_valuation_count INT;
    DECLARE previous_value BIGINT;
    DECLARE value_change_pct DECIMAL(10,2);

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;
    START TRANSACTION;

    IF NOT EXISTS (SELECT 1 FROM Player WHERE player_id = p_player_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Player ID does not exist';
    END IF;

    SELECT COUNT(*) INTO existing_valuation_count
    FROM PlayerValuation
    WHERE player_id = p_player_id AND date = p_valuation_date;

    IF existing_valuation_count > 0 THEN
        SELECT market_value_eur INTO previous_value
        FROM PlayerValuation
        WHERE player_id = p_player_id AND date = p_valuation_date;

        UPDATE PlayerValuation
        SET market_value_eur = p_market_value,
            current_club_id = p_club_id
        WHERE player_id = p_player_id AND date = p_valuation_date;

        IF previous_value IS NOT NULL AND previous_value > 0 THEN
            SET value_change_pct = ((p_market_value - previous_value) / previous_value) * 100;
            SELECT CONCAT('Valuation updated. Change: ', ROUND(value_change_pct, 2), '%') AS status;
        ELSE
            SELECT 'Valuation updated with new value' AS status;
        END IF;
    ELSE
        INSERT INTO PlayerValuation (player_id, date, market_value_eur, current_club_id)
        VALUES (p_player_id, p_valuation_date, p_market_value, p_club_id);
        SELECT 'New valuation record created' AS status;
    END IF;

    COMMIT;
END//

-- Stored Procedure 3: Get Player Career Summary
CREATE PROCEDURE GetPlayerCareerSummary(
    IN p_player_id INT,
    OUT p_player_name VARCHAR(150),
    OUT p_total_games INT,
    OUT p_total_goals INT,
    OUT p_total_assists INT,
    OUT p_total_minutes INT,
    OUT p_clubs_count INT,
    OUT p_current_club VARCHAR(100),
    OUT p_total_market_value BIGINT
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        RESIGNAL;
    END;

    SELECT p.name, c.name
    INTO p_player_name, p_current_club
    FROM Player p
    LEFT JOIN Club c ON p.current_club_id = c.club_id
    WHERE p.player_id = p_player_id;

    IF p_player_name IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Player not found';
    END IF;

    -- NOTE: aggregate Appearance and PlayerValuation separately. Joining them
    -- in one query fans out each appearance by the number of valuation rows,
    -- which inflates the goal/assist/minute sums.
    SELECT
        COUNT(DISTINCT a.game_id),
        SUM(a.goals),
        SUM(a.assists),
        SUM(a.minutes_played),
        COUNT(DISTINCT a.club_id)
    INTO p_total_games, p_total_goals, p_total_assists,
         p_total_minutes, p_clubs_count
    FROM Appearance a
    WHERE a.player_id = p_player_id;

    SELECT MAX(market_value_eur)
    INTO p_total_market_value
    FROM PlayerValuation
    WHERE player_id = p_player_id;
END//

-- Stored Procedure 4: Transfer Player Between Clubs
CREATE PROCEDURE TransferPlayer(
    IN p_player_id INT,
    IN p_from_club_id INT,
    IN p_to_club_id INT,
    IN p_transfer_date DATE,
    IN p_transfer_fee BIGINT,
    IN p_season VARCHAR(10)
)
BEGIN
    DECLARE current_club INT;
    DECLARE player_exists INT DEFAULT 0;
    DECLARE to_club_exists INT DEFAULT 0;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;
    START TRANSACTION;

    SELECT COUNT(*) INTO player_exists FROM Player WHERE player_id = p_player_id;
    IF player_exists = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Player ID does not exist';
    END IF;

    SELECT COUNT(*) INTO to_club_exists FROM Club WHERE club_id = p_to_club_id;
    IF to_club_exists = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Destination club does not exist';
    END IF;

    SELECT current_club_id INTO current_club FROM Player WHERE player_id = p_player_id;
    IF p_from_club_id IS NOT NULL AND (current_club IS NULL OR current_club != p_from_club_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Player is not currently at the specified from club';
    END IF;

    INSERT INTO Transfer (
        player_id, from_club_id, to_club_id,
        transfer_date, transfer_fee, season
    ) VALUES (
        p_player_id, current_club, p_to_club_id,
        p_transfer_date, p_transfer_fee, p_season
    );

    UPDATE Player SET current_club_id = p_to_club_id WHERE player_id = p_player_id;

    COMMIT;
    SELECT CONCAT('Player transferred successfully to club ID ', p_to_club_id) AS status;
END//

-- Stored Procedure 5: Get Top Performers by Position
CREATE PROCEDURE GetTopPerformersByPosition(
    IN p_position VARCHAR(30),
    IN p_season INT,
    IN p_min_games INT,
    IN p_limit INT
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        RESIGNAL;
    END;

    IF p_position IS NULL OR p_position = '' THEN
        SELECT
            p.player_id,
            p.name AS player_name,
            c.name AS club_name,
            p.position,
            COUNT(DISTINCT a.game_id) AS games_played,
            SUM(a.goals) AS total_goals,
            SUM(a.assists) AS total_assists,
            SUM(a.goals) + SUM(a.assists) AS goal_contributions,
            ROUND((SUM(a.goals) + SUM(a.assists)) * 90.0 / NULLIF(SUM(a.minutes_played), 0), 2) AS contributions_per_90,
            ROUND(SUM(a.minutes_played) / 90.0, 2) AS full_match_equivalent
        FROM Player p
        JOIN Appearance a ON p.player_id = a.player_id
        JOIN Club c ON p.current_club_id = c.club_id
        JOIN Game g ON a.game_id = g.game_id
        WHERE g.season = p_season
        GROUP BY p.player_id, p.name, c.name, p.position
        HAVING COUNT(DISTINCT a.game_id) >= p_min_games
        ORDER BY goal_contributions DESC
        LIMIT p_limit;
    ELSE
        SELECT
            p.player_id,
            p.name AS player_name,
            c.name AS club_name,
            p.position,
            COUNT(DISTINCT a.game_id) AS games_played,
            SUM(a.goals) AS total_goals,
            SUM(a.assists) AS total_assists,
            SUM(a.goals) + SUM(a.assists) AS goal_contributions,
            ROUND((SUM(a.goals) + SUM(a.assists)) * 90.0 / NULLIF(SUM(a.minutes_played), 0), 2) AS contributions_per_90,
            ROUND(SUM(a.minutes_played) / 90.0, 2) AS full_match_equivalent
        FROM Player p
        JOIN Appearance a ON p.player_id = a.player_id
        JOIN Club c ON p.current_club_id = c.club_id
        JOIN Game g ON a.game_id = g.game_id
        WHERE g.season = p_season
          AND p.position = p_position
        GROUP BY p.player_id, p.name, c.name, p.position
        HAVING COUNT(DISTINCT a.game_id) >= p_min_games
        ORDER BY goal_contributions DESC
        LIMIT p_limit;
    END IF;
END//

DELIMITER ;
