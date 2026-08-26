import pytest

from mev_lab.archive import Archive, ReceiptBundle
from mev_lab.audit import audit_archive
from mev_lab.decoder import CODEC, SWAP_TOPIC, decode_receipts
from mev_lab.fixtures import demo_archive


def _wire(*, metadata=None):
    pool, sender = "0x" + "01" * 20, "0x" + "02" * 20
    words = CODEC.encode(
        ["int256", "int256", "uint160", "uint128", "int24"],
        [10**19 + 1, -(10**19 + 3), 2**96, 50, 0],
    ).hex()
    log = {
        "address": pool, "logIndex": "0x0", "topics": [SWAP_TOPIC, "0x" + "00" * 32, "0x" + "00" * 32],
        "data": "0x" + words, **(metadata or {}),
    }
    return ReceiptBundle(
        chain_id=1,
        uniswap_v3_pools=[{"address": pool, "token0": sender, "token1": "0x" + "03" * 20,
                           "decimals0": 18, "decimals1": 18}],
        receipts=[{"blockNumber": "0xa", "transactionIndex": "0x0", "blockHash": "0x" + "04" * 32,
                   "transactionHash": "0x" + "05" * 32, "from": sender, "status": "0x1",
                   "effectiveGasPrice": "0x1", "gasUsed": "0x5208", "logs": [log]}],
    )


def test_decoder_rejects_mismatched_identity_and_topic_width():
    with pytest.raises(ValueError, match="blockNumber disagrees"):
        decode_receipts(_wire(metadata={"blockNumber": "0xb"}))
    capture = _wire()
    capture.receipts[0]["logs"][0]["topics"][-1] = "0x00"
    with pytest.raises(ValueError, match="indexed topic"):
        decode_receipts(capture)

def test_exact_abi_quantities_survive_the_normalized_archive():
    captured = decode_receipts(_wire())
    first = captured.transactions[0].swaps[0]
    assert first.amount_in_raw == str(10**19 + 1) and first.amount_out_raw == str(10**19 + 3)
    assert audit_archive(captured)["rows"][0]["gas_wei"] == "21000"

def test_declared_coverage_limits_ordering_candidates_and_keeps_protocol_events():
    original, truth, _ = demo_archive()
    data = original.model_dump()
    data["transaction_counts_by_block"] = {100: 4, 110: 3}
    report = audit_archive(Archive.model_validate(data), truth=truth, require_complete_blocks=True)
    assert [row["status"] for row in report["block_coverage"]] == ["partial", "complete", "unknown"]
    assert report["suppression_reasons"]["incomplete_capture"] == 4
    assert report["captured_liquidation_events"] == 1
    assert report["evaluation"]["macro_positive_f1"] is not None
