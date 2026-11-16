import hashlib

from scripts.content import generate_content


def test_s3_content_generator_writes_repeatable_bytes_and_manifest(tmp_path):
    first = generate_content(tmp_path / "first", 1024, 7)
    second = generate_content(tmp_path / "second", 1024, 7)
    first_path = tmp_path / "first" / "payload.bin"
    second_path = tmp_path / "second" / "payload.bin"

    assert first_path.stat().st_size == second_path.stat().st_size == 1024
    assert first_path.read_bytes() == second_path.read_bytes()
    assert first["sha256"] == hashlib.sha256(first_path.read_bytes()).hexdigest()
    assert (tmp_path / "first" / "manifest.json").exists()
