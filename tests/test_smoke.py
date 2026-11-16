from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_items_config_is_valid():
    items = yaml.safe_load((ROOT / "config" / "items.yaml").read_text(encoding="utf-8"))["items"]
    ids = [i["id"] for i in items]
    assert len(items) == 17
    assert len(ids) == len(set(ids)), "item ids must be unique"
    # every auction/operation family has both an announcement and a result
    for fam in ["cg", "sg", "tbill", "omo", "vrr", "vrrr"]:
        kinds = {i["kind"] for i in items if i["family"] == fam}
        assert kinds == {"announcement", "result"}
