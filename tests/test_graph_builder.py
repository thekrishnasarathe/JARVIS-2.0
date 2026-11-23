"""Tests for Graph Builder."""

from unittest.mock import MagicMock

from backend.modules.spatial_memory.graph_builder import build_graph_from_memory, node_from_new_memory


def test_node_from_new_memory():
    node = node_from_new_memory(1, "test content", "personal", 2)
    assert node.node_id == "mem_1"
    assert node.category == "personal"
    assert node.mass == 2.0
    assert len(node.pos) == 3


def test_build_graph_from_memory():
    mock_engine = MagicMock()
    # Mock tokenization
    mock_engine._tokenize.return_value = {"test": 1}
    mock_engine._cosine_similarity.return_value = 0.5

    # Mock db
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
        {
            "id": 1,
            "category": "test",
            "content": "hello test",
            "importance": 1,
            "pos_x": 0.0,
            "pos_y": 0.0,
            "pos_z": 0.0,
        },
        {
            "id": 2,
            "category": "test",
            "content": "another test",
            "importance": 1,
            "pos_x": None,
            "pos_y": None,
            "pos_z": None,
        },
    ]
    mock_engine.conn.cursor.return_value = mock_cursor

    nodes, edges = build_graph_from_memory(mock_engine)

    assert len(nodes) == 2
    assert nodes[0].pos[0] == 0.0
    assert len(edges) == 1
    assert edges[0] == ("mem_1", "mem_2", 0.5)
