CREATE TABLE document_chunk_geometry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id TEXT NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL CHECK (page_number > 0),
    original_text TEXT NOT NULL CHECK (length(original_text) > 0),
    normalized_text TEXT NOT NULL CHECK (length(normalized_text) > 0),
    block_id TEXT NOT NULL CHECK (length(block_id) BETWEEN 1 AND 128),
    span_id TEXT NOT NULL CHECK (length(span_id) BETWEEN 1 AND 128),
    bbox_x0 REAL NOT NULL,
    bbox_y0 REAL NOT NULL,
    bbox_x1 REAL NOT NULL,
    bbox_y1 REAL NOT NULL,
    page_width REAL NOT NULL,
    page_height REAL NOT NULL,
    CHECK (bbox_x0 >= 0 AND bbox_y0 >= 0),
    CHECK (bbox_x1 > bbox_x0 AND bbox_y1 > bbox_y0),
    CHECK (page_width > 0 AND page_height > 0),
    CHECK (bbox_x1 <= page_width AND bbox_y1 <= page_height),
    CHECK (page_width <= 1000000 AND page_height <= 1000000),
    UNIQUE (chunk_id, span_id)
);

CREATE INDEX document_chunk_geometry_chunk_page_idx
ON document_chunk_geometry(chunk_id, page_number, id);
