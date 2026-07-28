CREATE TABLE course_documents (
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    added_at TEXT NOT NULL,
    PRIMARY KEY (course_id, document_id)
);

CREATE INDEX course_documents_document_idx
ON course_documents(document_id, course_id);

INSERT INTO course_documents (course_id, document_id, added_at)
SELECT course_id, id, created_at
FROM documents
WHERE course_id IS NOT NULL;
