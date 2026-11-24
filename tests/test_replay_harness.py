from can_logger.replay_harness import TraceReplayHarness


def test_loader_keeps_payloads_that_look_like_numbers(tmp_path):
    # A payload made only of digits must stay a hex string, not become an integer.
    path = tmp_path / "digits.csv"
    path.write_text(
        "timestamp,arbitration_id,is_extended,dlc,data_hex\n"
        "0.001,0x100,False,8,0000000000000000\n"
        "0.002,0x100,False,8,1122334455667788\n"
    )

    frames = TraceReplayHarness(str(path)).load_frames()

    assert [f.data for f in frames] == [bytes(8), bytes.fromhex("1122334455667788")]
