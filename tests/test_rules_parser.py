import io, os, tempfile, textwrap, pytest
from socketcan_sa.rules import load_rules, RuleError

def _write_tmp(yaml_text: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".yaml")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(yaml_text))
    return path

def test_rules_valid_parsing_hex_and_dec():
    path = _write_tmp("""
        limits:
          "0x7DF": { rate: 10 }
          291:     { rate: 5, burst: 2 }  # 0x123 in decimal
        actions:
          drop:  [ "0x321", 999 ]
          remap: [ { from: "0x456", to: "0x457" } ]
    """)
    r = load_rules(path)
    # limits normalized
    assert r["limits"][0x7DF]["rate"] == 10
    assert r["limits"][0x123]["burst"] == 2
    # drop normalized
    assert 0x321 in r["drop"] and 999 in r["drop"]
    # remap dict
    assert r["remap"][0x456] == 0x457

def test_rules_invalid_cases():
    # negative rate
    path1 = _write_tmp('limits: {"0x7DF": { rate: -1 }}')
    with pytest.raises(RuleError):
        load_rules(path1)
    # burst < 1
    path2 = _write_tmp('limits: {"0x7DF": { rate: 5, burst: 0 }}')
    with pytest.raises(RuleError):
        load_rules(path2)
    # bad id
    path3 = _write_tmp('actions: { drop: ["xyz"] }')
    with pytest.raises(RuleError):
        load_rules(path3)
    # duplicate remap from
    path4 = _write_tmp("""
        actions:
          remap:
            - { from: "0x100", to: "0x101" }
            - { from: "0x100", to: "0x102" }
    """)
    with pytest.raises(RuleError):
        load_rules(path4)
    # out of range ID
    path5 = _write_tmp('actions: { drop: [0x20000000] }')  # > 29-bit
    with pytest.raises(RuleError):
        load_rules(path5)
