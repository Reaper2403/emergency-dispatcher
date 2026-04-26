from emergency_dispatcher.enhanced_audio import EnhancerStream


class DummyProcessor:
    def process(self, samples):
        return samples


def test_enhancer_stream_buffers_partial_chunks():
    stream = EnhancerStream(
        processor=DummyProcessor(),
        bytes_per_chunk=8,
    )

    assert stream.process_bytes(b"\x01\x00\x02\x00") == b""
    output = stream.process_bytes(b"\x03\x00\x04\x00")
    assert len(output) == 8
    assert stream.pending == bytearray()


def test_enhancer_stream_flush_preserves_tail_length():
    stream = EnhancerStream(
        processor=DummyProcessor(),
        bytes_per_chunk=8,
    )

    stream.process_bytes(b"\x01\x00\x02")
    output = stream.flush()
    assert len(output) == 3
    assert stream.pending == bytearray()
