"""In-memory stream behavior (no audio hardware needed)."""

from chasqui.core.audio import BytesStream, MultiOutputStream, NullStream


def test_bytes_stream_roundtrip():
    s = BytesStream(b"abcdef")
    assert s.read(4) == b"abcd"
    assert s.read(4) == b"ef"
    assert s.read(4) == b""

    s.write(b"out1")
    s.write(b"out2")
    assert s.output == b"out1out2"


def test_multi_output_fans_out():
    a, b = BytesStream(), BytesStream()
    multi = MultiOutputStream(a, b)
    multi.write(b"data")
    assert a.output == b"data"
    assert b.output == b"data"


def test_null_stream_is_noop():
    s = NullStream()
    s.write(b"data")
    assert s.read() == b""
    s.close()
