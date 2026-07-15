INSERT OR IGNORE INTO courses (id, title, description, created_at) VALUES
('course-calculus', 'Calculus I', 'Limits, derivatives, and applications.', '2026-07-01T09:00:00+00:00'),
('course-physics', 'Classical Mechanics', 'Motion, forces, energy, and momentum.', '2026-07-02T09:00:00+00:00');

INSERT OR IGNORE INTO concepts (id, course_id, name, bkt_slip, bkt_guess, bkt_transit) VALUES
('concept-chain-rule', 'course-calculus', 'Chain rule', 0.10, 0.20, 0.10),
('concept-limits', 'course-calculus', 'Limits', 0.10, 0.20, 0.10),
('concept-newton-2', 'course-physics', 'Newton second law', 0.08, 0.18, 0.09);

INSERT OR IGNORE INTO mastery (concept_id, probability, attempts, updated_at) VALUES
('concept-chain-rule', 0.42, 2, '2026-07-14T09:00:00+00:00'),
('concept-limits', 0.76, 4, '2026-07-13T09:00:00+00:00'),
('concept-newton-2', 0.58, 3, '2026-07-14T10:00:00+00:00');

INSERT OR IGNORE INTO study_tasks
    (id, course_id, concept_id, title, reason, due_at, estimated_minutes, status, created_at, updated_at)
VALUES
('task-chain-rule', 'course-calculus', 'concept-chain-rule', 'Review the chain rule',
 'Two recent attempts were incorrect and this concept is required for the next unit.',
 '2026-07-16T09:00:00+00:00', 20, 'upcoming', '2026-07-15T08:00:00+00:00', '2026-07-15T08:00:00+00:00'),
('task-newton', 'course-physics', 'concept-newton-2', 'Practice free-body diagrams',
 'Newton second law mastery is below the course target.',
 '2026-07-15T12:00:00+00:00', 25, 'overdue', '2026-07-14T08:00:00+00:00', '2026-07-14T08:00:00+00:00');
