from agent.repository.file_hash import generate_chunk_hash, generate_file_hash


def test_chunk_hash_ignores_trailing_whitespace_and_edge_blank_lines():
    clean = "def f():\n    return 1\n"
    messy = "\n\ndef f():   \n    return 1   \n\n\n"
    assert generate_chunk_hash(clean) == generate_chunk_hash(messy)


def test_chunk_hash_changes_on_real_edits():
    assert generate_chunk_hash("return 1") != generate_chunk_hash("return 2")


def test_chunk_hash_keeps_indentation_significant():
    # leading whitespace is syntax in Python; only *trailing* whitespace is cosmetic
    assert generate_chunk_hash("if x:\n    y") != generate_chunk_hash("if x:\ny")


def test_file_hash_is_exact_not_normalised():
    # Level-1 (file) hashing must notice whitespace edits so Level 2 can then
    # decide, per chunk, that nothing needs re-embedding.
    assert generate_file_hash("a ") != generate_file_hash("a")
