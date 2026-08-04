-- PitchStats database schema
-- 12-table relational design (from Checkpoint 2)
-- Target: MySQL 8.0

DROP DATABASE IF EXISTS pitchstats;
CREATE DATABASE pitchstats;
USE pitchstats;

CREATE TABLE Country (
  country_id INT PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE,
  confederation VARCHAR(20)
);

CREATE TABLE Stadium (
  stadium_id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(150) NOT NULL,
  city VARCHAR(100),
  capacity INT
);

CREATE TABLE Competition (
  competition_id VARCHAR(10) PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE,
  type VARCHAR(20) NOT NULL
);

CREATE TABLE Club (
  club_id INT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  type VARCHAR(30),
  squad_size INT,
  stadium_id INT,
  country_id INT,
  FOREIGN KEY (stadium_id) REFERENCES Stadium(stadium_id),
  FOREIGN KEY (country_id) REFERENCES Country(country_id)
);

CREATE TABLE ClubCompetition (
  competed_id INT AUTO_INCREMENT PRIMARY KEY,
  club_id INT NOT NULL,
  competition_id VARCHAR(10) NOT NULL,
  placement VARCHAR(20),
  FOREIGN KEY (club_id) REFERENCES Club(club_id),
  FOREIGN KEY (competition_id) REFERENCES Competition(competition_id),
  UNIQUE (club_id, competition_id)
);

CREATE TABLE Player (
  player_id INT PRIMARY KEY,
  name VARCHAR(150) NOT NULL,
  date_of_birth DATE,
  position VARCHAR(30),
  sub_position VARCHAR(50),
  foot VARCHAR(10),
  height INT,
  country_id INT,
  current_club_id INT,
  FOREIGN KEY (country_id) REFERENCES Country(country_id),
  FOREIGN KEY (current_club_id) REFERENCES Club(club_id)
);

CREATE TABLE Game (
  game_id INT PRIMARY KEY,
  date DATE NOT NULL,
  season INT NOT NULL,
  round VARCHAR(50),
  home_club_id INT NOT NULL,
  away_club_id INT NOT NULL,
  home_score INT,
  away_score INT,
  competition_id VARCHAR(10) NOT NULL,
  stadium_id INT,
  attendance INT,
  FOREIGN KEY (home_club_id) REFERENCES Club(club_id),
  FOREIGN KEY (away_club_id) REFERENCES Club(club_id),
  FOREIGN KEY (competition_id) REFERENCES Competition(competition_id),
  FOREIGN KEY (stadium_id) REFERENCES Stadium(stadium_id),
  CHECK (home_club_id != away_club_id)
);

CREATE TABLE Appearance (
  appearance_id INT AUTO_INCREMENT PRIMARY KEY,
  player_id INT NOT NULL,
  game_id INT NOT NULL,
  club_id INT NOT NULL,
  minutes_played INT DEFAULT 0,
  goals INT DEFAULT 0,
  assists INT DEFAULT 0,
  yellow_cards INT DEFAULT 0,
  red_cards INT DEFAULT 0,
  FOREIGN KEY (player_id) REFERENCES Player(player_id),
  FOREIGN KEY (game_id) REFERENCES Game(game_id),
  FOREIGN KEY (club_id) REFERENCES Club(club_id),
  UNIQUE (player_id, game_id)
);

CREATE TABLE GameEvent (
  event_id INT AUTO_INCREMENT PRIMARY KEY,
  game_id INT NOT NULL,
  player_id INT,
  club_id INT,
  event_type VARCHAR(30) NOT NULL,
  minute INT,
  description VARCHAR(255),
  FOREIGN KEY (game_id) REFERENCES Game(game_id),
  FOREIGN KEY (player_id) REFERENCES Player(player_id),
  FOREIGN KEY (club_id) REFERENCES Club(club_id)
);

CREATE TABLE PlayerValuation (
  valuation_id INT AUTO_INCREMENT PRIMARY KEY,
  player_id INT NOT NULL,
  date DATE NOT NULL,
  market_value_eur BIGINT,
  current_club_id INT,
  FOREIGN KEY (player_id) REFERENCES Player(player_id),
  FOREIGN KEY (current_club_id) REFERENCES Club(club_id),
  UNIQUE (player_id, date)
);

CREATE TABLE Transfer (
  transfer_id INT AUTO_INCREMENT PRIMARY KEY,
  player_id INT NOT NULL,
  from_club_id INT,
  to_club_id INT,
  transfer_date DATE,
  transfer_fee BIGINT DEFAULT 0,
  season VARCHAR(10),
  FOREIGN KEY (player_id) REFERENCES Player(player_id),
  FOREIGN KEY (from_club_id) REFERENCES Club(club_id),
  FOREIGN KEY (to_club_id) REFERENCES Club(club_id)
);

CREATE TABLE PlayerSeasonStats (
  stat_id INT AUTO_INCREMENT PRIMARY KEY,
  player_id INT NOT NULL,
  competition_id VARCHAR(10) NOT NULL,
  season INT NOT NULL,
  matches_played INT DEFAULT 0,
  starts INT DEFAULT 0,
  minutes_played INT DEFAULT 0,
  goals INT DEFAULT 0,
  assists INT DEFAULT 0,
  passing_accuracy DECIMAL(5,2),
  progressive_passes INT DEFAULT 0,
  shot_creating_actions INT DEFAULT 0,
  tackles INT DEFAULT 0,
  interceptions INT DEFAULT 0,
  blocks INT DEFAULT 0,
  FOREIGN KEY (player_id) REFERENCES Player(player_id),
  FOREIGN KEY (competition_id) REFERENCES Competition(competition_id),
  UNIQUE (player_id, competition_id, season)
);
