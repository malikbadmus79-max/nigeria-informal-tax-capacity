import pytest

from taxcap.load import list_members, load_config, read_table


def test_read_table_by_base_name(fake_zip):
    df = read_table("sect8b_harvestw5", zip_path=fake_zip)
    assert list(df.columns) == ["hhid", "ent_id", "s8q30"]
    assert len(df) == 2


def test_read_table_missing_raises(fake_zip):
    with pytest.raises(FileNotFoundError):
        read_table("does_not_exist", zip_path=fake_zip)


def test_list_members(fake_zip):
    assert len(list_members(fake_zip)) == 2


def test_config_has_threshold():
    assert load_config()["tax_rules"]["pit_exemption_naira"] == 800000
