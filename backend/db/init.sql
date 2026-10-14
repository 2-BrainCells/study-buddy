CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE videos (
    id           serial PRIMARY KEY,
    title        text NOT NULL,
    source       text NOT NULL,
    licence      text NOT NULL,
    duration_s   real,
    processed_at timestamptz
);

CREATE TABLE segments (
    id       serial PRIMARY KEY,
    video_id int  NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    start_s  real NOT NULL,
    end_s    real NOT NULL,
    text     text NOT NULL
);

CREATE TABLE terms (
    id          serial PRIMARY KEY,
    video_id    int  NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    term        text NOT NULL,
    first_ts    real NOT NULL,
    pause_ts    real NOT NULL,          -- sentence end after the term
    explanation text NOT NULL,
    embedding   vector(1024)            -- BGE-M3 output size
);

CREATE TABLE quiz_questions (
    id       serial PRIMARY KEY,
    video_id int   NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    term_id  int   NOT NULL REFERENCES terms(id)  ON DELETE CASCADE,
    question text  NOT NULL,
    options  jsonb NOT NULL,            -- list of strings
    answer   int   NOT NULL             -- index into options
);

CREATE TABLE learners (
    id            serial PRIMARY KEY,
    name          text NOT NULL,
    questionnaire jsonb,
    level         text
);

CREATE TABLE notes (
    id         serial PRIMARY KEY,
    learner_id int  NOT NULL REFERENCES learners(id) ON DELETE CASCADE,
    source     text NOT NULL CHECK (source IN ('typed', 'photo')),
    status     text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'reviewed')),
    text       text NOT NULL
);

CREATE TABLE learner_terms (
    learner_id int  NOT NULL REFERENCES learners(id) ON DELETE CASCADE,
    term_text  text NOT NULL,
    embedding  vector(1024),
    status     text NOT NULL CHECK (status IN ('known', 'new', 'rare', 'wrong')),
    source     text NOT NULL CHECK (source IN ('questionnaire', 'notes', 'video', 'quiz')),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (learner_id, term_text)
);

CREATE TABLE events (
    id         serial PRIMARY KEY,
    learner_id int  NOT NULL REFERENCES learners(id) ON DELETE CASCADE,
    video_id   int  NOT NULL REFERENCES videos(id)   ON DELETE CASCADE,
    type       text NOT NULL CHECK (type IN ('pause', 'glance', 'known', 'quiz_answer')),
    term_id    int  REFERENCES terms(id) ON DELETE CASCADE,
    correct    boolean,
    ts         real,                    -- position in the video, seconds
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE stage_costs (
    id            serial PRIMARY KEY,
    video_id      int REFERENCES videos(id)   ON DELETE SET NULL,
    learner_id    int REFERENCES learners(id) ON DELETE SET NULL,
    stage         text NOT NULL,
    model         text NOT NULL,
    requests      int  NOT NULL,
    input_tokens  int  NOT NULL,
    output_tokens int  NOT NULL,
    retries_429   int  NOT NULL,
    latency_ms    int  NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);