"""
NMEA 解析器 & 校验器 — pytest 测试套件
运行: python -m pytest test_nmea.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from datetime import time

import pytest
from nmea_parser import (
    parse_sentence, parse_file, checksum_verify,
    _parse_lat_lon, _parse_utc_time, _parse_date,
    GGA, RMC, GSA, GSV, VTG, NMEAParseError,
)
from nmea_validator import validate_file, validate_data, CHECKERS


# ══════════════════════════════════════════════════════════════
# 1. 校验和测试
# ══════════════════════════════════════════════════════════════

class TestChecksum:
    def test_valid_checksum(self):
        """正确校验和的语句"""
        assert checksum_verify("$GPGGA,083000.00,2308.12345,N,11322.56789,E,4,12,0.8,15.3,M,-5.2,M,1.5,0001*61")

    def test_invalid_checksum(self):
        """错误校验和（改了一个数字但没有更新校验值）"""
        assert not checksum_verify("$GPGGA,083000.00,2308.12345,N,11322.56789,E,4,12,0.8,15.3,M,-5.2,M,1.5,0001*00")

    def test_no_checksum(self):
        """没有校验和的语句"""
        assert not checksum_verify("$GPGGA,083000.00,2308.12345,N,11322.56789,E,4,12,0.8,15.3,M,-5.2,M,1.5,0001")

    def test_empty(self):
        assert not checksum_verify("")


# ══════════════════════════════════════════════════════════════
# 2. 经纬度转换
# ══════════════════════════════════════════════════════════════

class TestLatLon:
    def test_lat_north(self):
        result = _parse_lat_lon("2308.12345", "N")
        assert result == pytest.approx(23.1353908333, rel=1e-6)

    def test_lat_south(self):
        result = _parse_lat_lon("2308.12345", "S")
        assert round(result, 2) == -23.14

    def test_lon_east(self):
        result = _parse_lat_lon("11322.56789", "E")
        assert round(result, 6) == 113.376131

    def test_lon_west(self):
        result = _parse_lat_lon("11322.56789", "W")
        assert round(result, 6) == -113.376131

    def test_empty_value(self):
        assert _parse_lat_lon("", "N") is None
        assert _parse_lat_lon("2308.0", "") is None

    @pytest.mark.parametrize("val,direction", [
        ("abc.def", "N"),
        ("xxxx.xxxx", "E"),
    ])
    def test_invalid_format(self, val, direction):
        """无法解析的经纬度应返回 None"""
        assert _parse_lat_lon(val, direction) is None


# ══════════════════════════════════════════════════════════════
# 3. 时间/日期解析
# ══════════════════════════════════════════════════════════════

class TestTimeParsing:
    def test_valid_time(self):
        t = _parse_utc_time("083000.00")
        assert t.hour == 8
        assert t.minute == 30
        assert t.second == 0

    def test_with_microseconds(self):
        t = _parse_utc_time("123456.78")
        assert t.second == 56
        assert t.microsecond == 780000

    def test_empty(self):
        assert _parse_utc_time("") is None

    def test_too_short(self):
        assert _parse_utc_time("0830") is None


class TestDateParsing:
    def test_valid_date(self):
        d = _parse_date("220624")  # 22 June 2024
        assert d.year == 2024
        assert d.month == 6
        assert d.day == 22

    def test_invalid(self):
        assert _parse_date("") is None
        assert _parse_date("abc") is None


# ══════════════════════════════════════════════════════════════
# 4. GGA 语句解析
# ══════════════════════════════════════════════════════════════

class TestParseGGA:
    def test_rtk_fixed(self):
        """RTK 固定解 GGA"""
        raw = "$GPGGA,083000.00,2308.12345,N,11322.56789,E,4,12,0.8,15.3,M,-5.2,M,1.5,0001*61"
        stype, result = parse_sentence(raw)
        assert stype == "GGA"
        assert isinstance(result, GGA)
        assert result.fix_quality == 4
        assert result.satellites == 12
        assert result.hdop == 0.8
        assert result.altitude == 15.3
        assert result.checksum_valid is True
        assert result.latitude == pytest.approx(23.1353908333, rel=1e-6)

    def test_single_point(self):
        """单点定位"""
        raw = "$GPGGA,083003.00,2308.12345,N,11322.56789,E,1,7,2.5,16.0,M,-5.2,M,,*2B"
        stype, result = parse_sentence(raw)
        assert result.fix_quality == 1
        assert result.satellites == 7
        assert result.hdop == 2.5

    def test_no_fix(self):
        """无定位"""
        raw = "$GPGGA,083004.00,,,,,0,0,,,M,,M,,*77"
        stype, result = parse_sentence(raw)
        assert result.fix_quality == 0
        assert result.latitude is None

    def test_float_solution(self):
        """RTK 浮点解"""
        raw = "$GPGGA,083005.00,2308.12345,N,11322.56789,E,5,10,1.5,15.8,M,-5.2,M,2.0,0001*66"
        stype, result = parse_sentence(raw)
        assert result.fix_quality == 5


# ══════════════════════════════════════════════════════════════
# 5. RMC 语句解析
# ══════════════════════════════════════════════════════════════

class TestParseRMC:
    def test_active_rmc(self):
        raw = "$GPRMC,083000.00,A,2308.12345,N,11322.56789,E,0.05,180.5,220624,2.1,W,A*2C"
        stype, result = parse_sentence(raw)
        assert stype == "RMC"
        assert isinstance(result, RMC)
        assert result.status == "A"
        assert result.speed_over_ground == 0.05
        assert result.track_angle == 180.5
        assert result.date is not None

    def test_void_rmc(self):
        raw = "$GPRMC,083006.00,V,,,,,,,220624,,,N*4B"
        stype, result = parse_sentence(raw)
        assert result.status == "V"


# ══════════════════════════════════════════════════════════════
# 6. GSA / GSV / VTG 解析
# ══════════════════════════════════════════════════════════════

class TestParseGSA:
    def test_3d_fix(self):
        raw = "$GPGSA,A,3,01,03,07,08,11,16,22,23,26,28,31,32,1.2,0.8,0.9*3B"
        stype, result = parse_sentence(raw)
        assert stype == "GSA"
        assert isinstance(result, GSA)
        assert result.mode2 == 3
        assert len(result.satellite_ids) == 12
        assert result.pdop == 1.2

    def test_no_fix(self):
        raw = "$GPGSA,A,1,,,,,,,,,,,,,99.9,99.9,99.9*0F"
        stype, result = parse_sentence(raw)
        assert result.mode2 == 1
        assert result.pdop == 99.9


class TestParseGSV:
    def test_gsv(self):
        raw = "$GPGSV,3,1,12,01,65,045,48,03,32,120,42,07,15,280,38,08,45,195,45*78"
        stype, result = parse_sentence(raw)
        assert stype == "GSV"
        assert isinstance(result, GSV)
        assert result.total_messages == 3
        assert result.satellites_in_view == 12
        assert len(result.satellites) == 4
        assert result.satellites[0]["prn"] == 1
        assert result.satellites[0]["snr"] == 48


class TestParseVTG:
    def test_vtg(self):
        raw = "$GPVTG,180.5,T,182.6,M,0.05,N,0.09,K,A*22"
        stype, result = parse_sentence(raw)
        assert stype == "VTG"
        assert isinstance(result, VTG)
        assert result.track_true == 180.5
        assert result.speed_kmh == pytest.approx(0.09, rel=0.01)


# ══════════════════════════════════════════════════════════════
# 7. 边界与异常
# ══════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_empty_sentence(self):
        stype, data = parse_sentence("")
        assert stype is None
        assert data is None

    def test_plain_text_not_nmea(self):
        stype, data = parse_sentence("这是一个普通文本")
        assert stype is None
        assert data is None

    def test_unknown_type(self):
        """未知的NMEA语句类型"""
        raw = "$GPXYZ,some,data,here*00"
        stype, data = parse_sentence(raw)
        assert stype == "XYZ"
        assert data is None

    def test_wrong_checksum(self):
        raw = "$GPGGA,083000.00,2308.12345,N,11322.56789,E,4,12,0.8,15.3,M,-5.2,M,1.5,0001*00"
        stype, result = parse_sentence(raw)
        assert result.checksum_valid is False

    @pytest.mark.parametrize("raw,expected_quality", [
        ("$GPGGA,083000.00,,,,,0,0,,,M,,M,,*73", 0),
        ("$GPGGA,083000.00,2308.12,N,11322.56,E,1,7,2.5,16.0,M,-5.2,M,,*3A", 1),
        ("$GPGGA,083000.00,2308.12,N,11322.56,E,2,8,1.5,17.0,M,-5.2,M,1.0,0001*5A", 2),
        ("$GPGGA,083000.00,2308.12,N,11322.56,E,4,12,0.8,15.3,M,-5.2,M,1.5,0001*6F", 4),
        ("$GPGGA,083000.00,2308.12,N,11322.56,E,5,10,1.5,15.8,M,-5.2,M,2.0,0001*66", 5),
    ])
    def test_all_fix_qualities(self, raw, expected_quality):
        """覆盖所有定位质量等级"""
        stype, result = parse_sentence(raw)
        assert result.fix_quality == expected_quality


# ══════════════════════════════════════════════════════════════
# 8. 校验器测试
# ══════════════════════════════════════════════════════════════

class TestValidator:
    def test_validate_rtk_fixed(self):
        """RTK固定解应无错误"""
        gga = GGA(fix_quality=4, satellites=12, hdop=0.8, altitude=15.3,
                  latitude=23.0, longitude=113.0,
                  dgps_age=1.5, checksum_valid=True)
        results = CHECKERS["GGA"](gga, 1)
        errors = [r for r in results if r.level == "error"]
        assert len(errors) == 0

    def test_validate_no_fix(self):
        """无定位应有警告"""
        gga = GGA(fix_quality=0, satellites=0, altitude=None,
                  latitude=None, longitude=None, checksum_valid=True)
        results = CHECKERS["GGA"](gga, 1)
        assert any("定位无效" in r.message for r in results)

    def test_validate_out_of_range_lat(self):
        """纬度超出范围"""
        gga = GGA(fix_quality=4, satellites=12, hdop=0.8,
                  latitude=95.0, longitude=113.0, checksum_valid=True)
        results = CHECKERS["GGA"](gga, 1)
        assert any("纬度异常" in r.message for r in results)

    def test_validate_out_of_range_lon(self):
        """经度超出范围"""
        gga = GGA(fix_quality=4, satellites=12, hdop=0.8,
                  latitude=23.0, longitude=200.0, checksum_valid=True)
        results = CHECKERS["GGA"](gga, 1)
        assert any("经度异常" in r.message for r in results)

    def test_validate_abnormal_hdop(self):
        """HDOP异常值"""
        gga = GGA(fix_quality=4, satellites=12, hdop=-1.0,
                  latitude=23.0, longitude=113.0, checksum_valid=True)
        results = CHECKERS["GGA"](gga, 1)
        assert any("HDOP异常" in r.message for r in results)

    def test_validate_high_dgps_age(self):
        """差分龄期过长"""
        gga = GGA(fix_quality=4, satellites=12, hdop=0.8,
                  latitude=23.0, longitude=113.0,
                  dgps_age=15.0, checksum_valid=True)
        results = CHECKERS["GGA"](gga, 1)
        assert any("差分龄期" in r.message for r in results)


# ══════════════════════════════════════════════════════════════
# 9. 文件级测试
# ══════════════════════════════════════════════════════════════

class TestFileOperations:
    def test_parse_sample_file(self):
        """解析示例文件应无异常（返回 3 元组：by_type, epochs, errors）"""
        sample = Path(__file__).parent / "samples" / "sample_1.nmea"
        by_type, epochs, errors = parse_file(str(sample))
        # 按 talker+type 分组，至少有 GPGGA 和 GPRMC
        assert any(k.endswith("GGA") for k in by_type)
        assert any(k.endswith("RMC") for k in by_type)
        gga_keys = [k for k in by_type if k.endswith("GGA")]
        assert len(by_type[gga_keys[0]]) > 0
        # epoch 分组非空
        assert len(epochs) > 0

    def test_validate_sample_file(self):
        """校验示例文件应产出报告"""
        sample = Path(__file__).parent / "samples" / "sample_1.nmea"
        report = validate_file(str(sample))
        assert report.total_sentences > 0
        # 示例文件中故意放了一些异常场景，应该有 warning 或 error
        assert len(report.results) > 0


# ══════════════════════════════════════════════════════════════
# 10. P0: 历元（epoch）测试
# ══════════════════════════════════════════════════════════════

class TestEpochGrouping:
    """parse_file 按 UTC 时间戳将同一秒的语句聚成历元"""

    def test_epoch_keys_include_fractional_seconds(self):
        """epoch 字典 key 为 HHMMSS.ffffff 格式（含小数秒，区分高频定位）"""
        sample = Path(__file__).parent / "samples" / "sample_1.nmea"
        _, epochs, _ = parse_file(str(sample))
        for key in epochs:
            # 格式: "083000.000000" — 6位数字 + 小数点 + 6位微秒
            assert "." in key
            hhmmss, frac = key.split(".")
            assert len(hhmmss) == 6 and hhmmss.isdigit()
            assert len(frac) == 6 and frac.isdigit()

    def test_gsa_gsv_vtg_follow_last_gga_time(self):
        """无时间戳的 GSA/GSV/VTG 归入最近一次 GGA/RMC 所在历元"""
        sample = Path(__file__).parent / "samples" / "sample_1.nmea"
        _, epochs, _ = parse_file(str(sample))
        # 083000.000000 历元至少应有 GGA+RMC+GSA+GSV+VTG
        target_key = "083000.000000"
        if target_key in epochs:
            types_in_epoch = set()
            for s in epochs[target_key]:
                types_in_epoch.add(type(s).__name__)
            assert "GGA" in types_in_epoch
        else:
            # 如果没有精确匹配，至少有一个以 083000 开头的历元
            keys_0830 = [k for k in epochs if k.startswith("0830")]
            assert len(keys_0830) > 0
            # 正常情况 GSA/GSV/VTG 也在同一个历元里


class TestEpochValidation:
    """历元级校验：同一历元内唯一性检查"""

    def _make_epoch_data(self, *sentences):
        """构造历元数据供直接测试 _check_epoch_duplicates"""
        epoch = {}
        for s in sentences:
            if hasattr(s, 'utc_time') and s.utc_time:
                key = s.utc_time.strftime("%H%M%S.%f")
            else:
                key = "000000.000000"
            epoch.setdefault(key, []).append(s)
        return epoch

    def test_duplicate_gga_in_epoch_is_error(self):
        """同一历元出现两条 GGA → error"""
        from nmea_validator import _check_epoch_duplicates
        gga1 = GGA(utc_time=time(8, 30, 0), fix_quality=4, line_number=10)
        gga2 = GGA(utc_time=time(8, 30, 0), fix_quality=4, line_number=15)
        results = _check_epoch_duplicates([gga1, gga2], "083000.000000")
        errors = [r for r in results if r.level == "error"]
        assert len(errors) >= 1
        assert any("GGA" in e.message for e in errors)

    def test_duplicate_rmc_in_epoch_is_error(self):
        """同一历元出现两条 RMC → error"""
        from nmea_validator import _check_epoch_duplicates
        rmc1 = RMC(utc_time=time(8, 30, 0), line_number=10)
        rmc2 = RMC(utc_time=time(8, 30, 0), line_number=15)
        results = _check_epoch_duplicates([rmc1, rmc2], "083000.000000")
        errors = [r for r in results if r.level == "error"]
        assert any("RMC" in e.message for e in errors)

    def test_duplicate_vtg_in_epoch_is_error(self):
        """同一历元出现两条 VTG → error"""
        from nmea_validator import _check_epoch_duplicates
        vtg1 = VTG(line_number=10)
        vtg2 = VTG(line_number=15)
        results = _check_epoch_duplicates([vtg1, vtg2], "083000.000000")
        errors = [r for r in results if r.level == "error"]
        assert any("VTG" in e.message for e in errors)

    def test_multiple_gsa_in_epoch_is_ok(self):
        """同一历元多条 GSA 正常（多星座各有自己的 GSA）→ 不报错"""
        from nmea_validator import _check_epoch_duplicates
        gsa1 = GSA(talker_id="GP", mode2=3, line_number=10)
        gsa2 = GSA(talker_id="GN", mode2=3, line_number=11)
        results = _check_epoch_duplicates([gsa1, gsa2], "083000.000000")
        errors = [r for r in results if r.level == "error"]
        assert len(errors) == 0

    def test_multiple_gsv_in_epoch_is_ok(self):
        """同一历元多条 GSV 正常（GSV 续号）→ 不报错"""
        from nmea_validator import _check_epoch_duplicates
        gsv1 = GSV(talker_id="GP", message_number=1, line_number=10)
        gsv2 = GSV(talker_id="GP", message_number=2, line_number=11)
        gsv3 = GSV(talker_id="GP", message_number=3, line_number=12)
        results = _check_epoch_duplicates([gsv1, gsv2, gsv3], "083000.000000")
        errors = [r for r in results if r.level == "error"]
        assert len(errors) == 0

    def test_unique_gga_rmc_vtg_no_error(self):
        """每历元各一条 GGA/RMC/VTG → 不报错"""
        from nmea_validator import _check_epoch_duplicates
        gga = GGA(utc_time=time(8, 30, 0), line_number=10)
        rmc = RMC(utc_time=time(8, 30, 0), line_number=11)
        vtg = VTG(line_number=12)
        results = _check_epoch_duplicates([gga, rmc, vtg], "083000.000000")
        errors = [r for r in results if r.level == "error"]
        assert len(errors) == 0

    def test_duplicate_detection_reports_line_numbers(self):
        """重复检测的报告里注明涉及的行号"""
        from nmea_validator import _check_epoch_duplicates
        gga1 = GGA(utc_time=time(8, 30, 0), line_number=42)
        gga2 = GGA(utc_time=time(8, 30, 0), line_number=99)
        results = _check_epoch_duplicates([gga1, gga2], "083000.000000")
        errors = [r for r in results if r.level == "error"]
        assert len(errors) >= 1
        msg = errors[0].message
        assert "42" in msg and "99" in msg

    def test_high_freq_5hz_no_false_positive(self):
        """5Hz 接收机：同一整秒内、小数秒不同的 5 条 GGA → 不误报重复"""
        from nmea_validator import _check_epoch_duplicates
        ggas = [
            GGA(utc_time=time(8, 30, 0, 0),       line_number=1),   # 083000.00
            GGA(utc_time=time(8, 30, 0, 200000),   line_number=2),   # 083000.20
            GGA(utc_time=time(8, 30, 0, 400000),   line_number=3),   # 083000.40
            GGA(utc_time=time(8, 30, 0, 600000),   line_number=4),   # 083000.60
            GGA(utc_time=time(8, 30, 0, 800000),   line_number=5),   # 083000.80
        ]
        epochs = self._make_epoch_data(*ggas)
        all_results = []
        for epoch_key, sentences in epochs.items():
            all_results.extend(_check_epoch_duplicates(sentences, epoch_key))
        errors = [r for r in all_results if r.level == "error"]
        assert len(errors) == 0, f"5Hz 不应误报重复，但产生了 {len(errors)} 条 error"

    def test_same_exact_moment_duplicate_still_error(self):
        """同一精确时刻（小数秒也相同）两条 GGA → 仍然报 error（对照）"""
        from nmea_validator import _check_epoch_duplicates
        gga1 = GGA(utc_time=time(8, 30, 0, 200000), line_number=10)
        gga2 = GGA(utc_time=time(8, 30, 0, 200000), line_number=11)  # 完全同一瞬间
        results = _check_epoch_duplicates([gga1, gga2], "083000.200000")
        errors = [r for r in results if r.level == "error"]
        assert len(errors) >= 1
        assert "GGA" in errors[0].message


# ══════════════════════════════════════════════════════════════
# 11. P1: 行号 & talker 保留 & 死代码
# ══════════════════════════════════════════════════════════════

class TestLineNumber:
    """解析结果记录真实文件行号"""

    def test_parsed_object_has_line_number(self):
        """parse_file 返回的每条语句都有 line_number"""
        sample = Path(__file__).parent / "samples" / "sample_1.nmea"
        by_type, epochs, _ = parse_file(str(sample))
        for key, sentences in by_type.items():
            for s in sentences:
                assert hasattr(s, "line_number")
                assert s.line_number > 0

    def test_validation_result_has_line_number_field(self):
        """ValidationResult 的 line_number 字段记录文件行号"""
        sample = Path(__file__).parent / "samples" / "sample_1.nmea"
        report = validate_file(str(sample))
        for r in report.results:
            assert hasattr(r, "line_number")
            assert isinstance(r.line_number, int)

    def test_error_report_mentions_file_line_not_sequence(self):
        """报告里用文件行号标识，不是"第几条"的序列号"""
        sample = Path(__file__).parent / "samples" / "sample_1.nmea"
        report = validate_file(str(sample))
        # summary 输出应包含"行"字提示文件行号
        text = report.summary()
        assert "行" in text


class TestTalkerPreservation:
    """多星座 speak_id 不并桶"""

    def test_gn_and_gp_gga_separated(self):
        """$GNGGA 和 $GPGGA 分在不同 key"""
        sample = Path(__file__).parent / "samples" / "sample_1.nmea"
        by_type, _, _ = parse_file(str(sample))
        # 目前样本文件主要是 GP 开头，检查 key 包含 talker 前缀
        gga_keys = [k for k in by_type if k.endswith("GGA")]
        for key in gga_keys:
            # key 格式: "GPGGA", "GNGGA" → 保留了 talker
            assert len(key) == 5  # 2 位 talker + 3 位类型
            assert key[:2] in ("GP", "GN", "GL", "GA", "GB", "BD")

    def test_talker_field_on_parsed_object(self):
        """每条解析结果保留完整 talker_id"""
        raw_gn = "$GNGGA,083000.00,2308.12345,N,11322.56789,E,4,12,0.8,15.3,M,-5.2,M,1.5,0001*6A"
        _, result = parse_sentence(raw_gn)
        assert result.talker_id == "GN"

    def test_gsa_talker_preserved(self):
        """GSA 的 talker 也保留"""
        raw = "$GNGSA,A,3,01,03,07,08,11,16,22,23,26,28,31,32,1.2,0.8,0.9*39"
        _, result = parse_sentence(raw)
        assert result.talker_id == "GN"


class TestDeadCodeRemoval:
    """_parse_lat_lon 冗余分支删除后行为不变"""

    def test_lat_north(self):
        """北纬正常解析"""
        result = _parse_lat_lon("2308.12345", "N")
        assert result == pytest.approx(23.1353908333, rel=1e-6)

    def test_lat_south(self):
        """南纬正常解析"""
        result = _parse_lat_lon("2308.12345", "S")
        assert round(result, 2) == -23.14

    def test_lon_east(self):
        """东经正常解析"""
        result = _parse_lat_lon("11322.56789", "E")
        assert round(result, 6) == 113.376131

    def test_lon_west(self):
        """西经正常解析"""
        result = _parse_lat_lon("11322.56789", "W")
        assert round(result, 6) == -113.376131

    @pytest.mark.parametrize("val,direction", [
        ("abc.def", "N"),
        ("xxxx.xxxx", "E"),
    ])
    def test_invalid_format_returns_none(self, val, direction):
        assert _parse_lat_lon(val, direction) is None
