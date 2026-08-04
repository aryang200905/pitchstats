-- PitchStats views
USE pitchstats;

DROP VIEW IF EXISTS PlayerCareerView;
DROP VIEW IF EXISTS ClubCompetitionPerformanceView;

-- Per-player career aggregates from Appearance, with current club name.
CREATE VIEW PlayerCareerView AS
SELECT
    p.player_id,
    p.name                              AS player_name,
    p.position,
    c.name                              AS current_club,
    COUNT(a.appearance_id)              AS total_games,
    COALESCE(SUM(a.goals), 0)           AS total_goals,
    COALESCE(SUM(a.assists), 0)         AS total_assists,
    COALESCE(SUM(a.minutes_played), 0)  AS total_minutes,
    COUNT(DISTINCT a.club_id)           AS clubs_count
FROM Player p
LEFT JOIN Appearance a ON a.player_id = p.player_id
LEFT JOIN Club c       ON c.club_id = p.current_club_id
GROUP BY p.player_id, p.name, p.position, c.name;

-- Per-club, per-competition win/draw/loss and goal aggregates.
CREATE VIEW ClubCompetitionPerformanceView AS
SELECT
    club_id,
    competition_id,
    COUNT(*)                                             AS matches,
    SUM(is_win)                                          AS wins,
    SUM(is_draw)                                         AS draws,
    SUM(is_loss)                                         AS losses,
    SUM(goals_for)                                       AS goals_for,
    SUM(goals_against)                                   AS goals_against
FROM (
    SELECT g.home_club_id AS club_id, g.competition_id,
           CASE WHEN g.home_score > g.away_score THEN 1 ELSE 0 END AS is_win,
           CASE WHEN g.home_score = g.away_score THEN 1 ELSE 0 END AS is_draw,
           CASE WHEN g.home_score < g.away_score THEN 1 ELSE 0 END AS is_loss,
           g.home_score AS goals_for, g.away_score AS goals_against
    FROM Game g
    UNION ALL
    SELECT g.away_club_id AS club_id, g.competition_id,
           CASE WHEN g.away_score > g.home_score THEN 1 ELSE 0 END AS is_win,
           CASE WHEN g.away_score = g.home_score THEN 1 ELSE 0 END AS is_draw,
           CASE WHEN g.away_score < g.home_score THEN 1 ELSE 0 END AS is_loss,
           g.away_score AS goals_for, g.home_score AS goals_against
    FROM Game g
) t
GROUP BY club_id, competition_id;
