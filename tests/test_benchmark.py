from can_logger.benchmark import run_benchmark


def test_benchmark_accounts_for_every_frame_when_the_buffer_is_big_enough():
    result = run_benchmark(n_frames=2000, buffer_capacity=100000)

    assert result["frames_sent"] == 2000
    assert result["frames_decoded"] == 2000
    assert result["dropped_frames"] == 0
    assert result["frames_per_second"] > 0


def test_benchmark_decoded_plus_dropped_always_equals_sent():
    result = run_benchmark(n_frames=5000, buffer_capacity=10)

    assert result["frames_decoded"] + result["dropped_frames"] == result["frames_sent"]
    assert result["p99_decode_ms"] >= result["p50_decode_ms"] >= 0
