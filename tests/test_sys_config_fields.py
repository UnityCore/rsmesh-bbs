from rsmesh_bbs.sys_config_fields import bool_value_to_yn, validate_sys_config_value


class TestSysConfigFieldValidation:
    def test_bool_validation_accepts_yn(self):
        valid, value, error = validate_sys_config_value("bbs", "send_urgent_alert_local", "Y")
        assert valid is True
        assert value == "true"
        assert error is None
        assert bool_value_to_yn("false") == "N"

    def test_node_id_validation(self):
        valid, value, _error = validate_sys_config_value("interface", "node_id", "!17D7E4B7")
        assert valid is True
        assert value == "!17d7e4b7"

        valid, _value, error = validate_sys_config_value("interface", "node_id", "bad")
        assert valid is False
        assert error

    def test_enum_validation(self):
        valid, value, _error = validate_sys_config_value("interface", "type", "serial")
        assert valid is True
        assert value == "serial"

        valid, _value, error = validate_sys_config_value("interface", "type", "usb")
        assert valid is False
        assert error

    def test_int_min_validation(self):
        valid, value, _error = validate_sys_config_value("schedule", "peer_sync_minutes", "5")
        assert valid is True
        assert value == "5"

        valid, _value, error = validate_sys_config_value("schedule", "peer_sync_minutes", "0")
        assert valid is False
        assert error
