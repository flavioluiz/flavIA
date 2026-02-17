import hashlib
from pathlib import Path

from flavia.content.indexer.chunker import chunk_document, chunk_text_document, chunk_video_document


def test_chunk_document_video_includes_visual_frame_chunks(tmp_path: Path):
    converted_dir = tmp_path / ".converted"
    converted_dir.mkdir()

    transcript_path = converted_dir / "lecture.md"
    transcript_path.write_text(
        "# Lecture\n\n"
        "## Transcription\n\n"
        "[00:10 - 00:20] We define the convolution operation."
    )

    frame_dir = converted_dir / "lecture_frames"
    frame_dir.mkdir()
    frame_path = frame_dir / "frame_00m30s.md"
    frame_path.write_text(
        "# Visual Frame at 00:30\n\n"
        "---\n"
        "video_source: `lecture.mp4`\n"
        "timestamp: 00:30\n"
        "---\n\n"
        "## Description\n\n"
        "The slide shows a 3x3 convolution kernel."
    )

    entry = {
        "path": "lecture.mp4",
        "name": "lecture.mp4",
        "file_type": "video",
        "converted_to": ".converted/lecture.md",
        "frame_descriptions": [".converted/lecture_frames/frame_00m30s.md"],
    }

    chunks = chunk_document(entry, tmp_path)
    modalities = {chunk["modality"] for chunk in chunks}
    assert "video_transcript" in modalities
    assert "video_frame" in modalities

    frame_chunks = [chunk for chunk in chunks if chunk["modality"] == "video_frame"]
    assert len(frame_chunks) == 1
    assert "3x3 convolution kernel" in frame_chunks[0]["text"]
    assert frame_chunks[0]["source"]["locator"]["time_start"] == "00:00:30"


def test_chunk_document_video_parses_timestamp_ranges_without_metadata(tmp_path: Path):
    converted_dir = tmp_path / ".converted"
    converted_dir.mkdir()

    transcript_path = converted_dir / "class.md"
    transcript_path.write_text(
        "# Class\n\n"
        "---\n"
        "source_file: `class.mp4`\n"
        "---\n\n"
        "## Transcription\n\n"
        "[00:10 - 00:20] First segment.\n\n"
        "[00:21 - 00:35] Second segment."
    )

    entry = {
        "path": "class.mp4",
        "name": "class.mp4",
        "file_type": "video",
        "converted_to": ".converted/class.md",
        "frame_descriptions": [],
    }

    chunks = chunk_document(entry, tmp_path)
    assert len(chunks) == 1

    chunk = chunks[0]
    assert chunk["modality"] == "video_transcript"
    assert chunk["source"]["locator"]["time_start"] == "00:00:10"
    assert chunk["source"]["locator"]["time_end"] == "00:00:35"
    assert "# Class" not in chunk["text"]
    assert "source_file:" not in chunk["text"]
    assert "First segment." in chunk["text"]
    assert "Second segment." in chunk["text"]


def test_chunk_document_rejects_converted_path_traversal(tmp_path: Path):
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    (tmp_path / "outside.md").write_text("secret content")

    entry = {
        "path": "paper.pdf",
        "name": "paper.pdf",
        "file_type": "binary_document",
        "converted_to": "../outside.md",
    }

    assert chunk_document(entry, vault_dir) == []


def test_chunk_document_rejects_frame_path_traversal(tmp_path: Path):
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    converted_dir = vault_dir / ".converted"
    converted_dir.mkdir()

    transcript_path = converted_dir / "lecture.md"
    transcript_path.write_text("## Transcription\n\n[00:10 - 00:20] Safe transcript content.")
    (tmp_path / "outside_frame.md").write_text(
        "# Visual Frame at 00:30\n\n## Description\n\nLeaked frame content."
    )

    entry = {
        "path": "lecture.mp4",
        "name": "lecture.mp4",
        "file_type": "video",
        "converted_to": ".converted/lecture.md",
        "frame_descriptions": ["../outside_frame.md"],
    }

    chunks = chunk_document(entry, vault_dir)
    assert len(chunks) == 1
    assert chunks[0]["modality"] == "video_transcript"


def test_chunk_document_video_fallback_keeps_single_doc_id(tmp_path: Path):
    converted_dir = tmp_path / ".converted"
    converted_dir.mkdir()

    transcript_path = converted_dir / "lecture.md"
    transcript_path.write_text("Transcript without explicit timestamps.")

    frame_path = converted_dir / "frame_00m30s.md"
    frame_path.write_text(
        "# Visual Frame at 00:30\n\n## Description\n\nA timeline diagram is visible."
    )

    entry = {
        "path": "lecture.mp4",
        "name": "lecture.mp4",
        "file_type": "video",
        "converted_to": ".converted/lecture.md",
        "frame_descriptions": [".converted/frame_00m30s.md"],
    }

    chunks = chunk_document(entry, tmp_path)
    modalities = {chunk["modality"] for chunk in chunks}
    assert "video_transcript" in modalities
    assert "video_frame" in modalities
    assert len({chunk["doc_id"] for chunk in chunks}) == 1


def test_chunk_text_document_uses_real_line_numbers(tmp_path: Path):
    converted_dir = tmp_path / ".converted"
    converted_dir.mkdir()

    body = " ".join(["token"] * 260)  # keep above minimum chunk size threshold
    converted_path = converted_dir / "paper.md"
    converted_path.write_text("# Section\n\n" + body)

    entry = {
        "path": "paper.pdf",
        "name": "paper.pdf",
        "file_type": "binary_document",
        "converted_to": ".converted/paper.md",
    }

    chunks = chunk_document(entry, tmp_path)
    assert len(chunks) == 1
    assert chunks[0]["source"]["locator"]["line_start"] == 3
    assert chunks[0]["source"]["locator"]["line_end"] == 3


def test_chunk_document_uses_original_checksum_for_doc_id(tmp_path: Path):
    converted_dir = tmp_path / ".converted"
    converted_dir.mkdir()
    converted_path = converted_dir / "paper.md"
    converted_path.write_text("A " * 2000, encoding="utf-8")

    entry = {
        "path": "paper.pdf",
        "name": "paper.pdf",
        "file_type": "binary_document",
        "converted_to": ".converted/paper.md",
        "checksum_sha256": "sha-original-file",
    }

    chunks = chunk_document(entry, tmp_path)
    assert chunks

    expected_doc_id = hashlib.sha1(f"{tmp_path}:paper.pdf:sha-original-file".encode()).hexdigest()
    assert chunks[0]["doc_id"] == expected_doc_id


def test_chunk_text_document_rejects_outside_base_dir(tmp_path: Path):
    base_dir = tmp_path / "vault"
    base_dir.mkdir()
    outside_path = tmp_path / "outside.md"
    outside_path.write_text("secret")

    chunks = chunk_text_document(
        converted_path=outside_path,
        source_name="outside.md",
        file_type="text",
        base_dir=base_dir,
        original_path="outside.md",
    )
    assert chunks == []


def test_chunk_video_document_rejects_outside_base_dir(tmp_path: Path):
    base_dir = tmp_path / "vault"
    base_dir.mkdir()
    outside_transcript = tmp_path / "outside_video.md"
    outside_transcript.write_text("## Transcription\n\n[00:10 - 00:20] Secret transcript.")

    chunks = chunk_video_document(
        converted_path=outside_transcript,
        source_name="outside_video.mp4",
        base_dir=base_dir,
        original_path="outside_video.mp4",
        frame_desc_paths=None,
    )
    assert chunks == []
