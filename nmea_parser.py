"""
NMEA-0183 语句解析器
支持：GGA, RMC, GSA, GSV, VTG
"""

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Optional


class NMEAParseError(Exception):
    """NMEA 解析异常"""
    pass


# ─── 数据类定义 ────────────────────────────────────────────


@dataclass
class GGA:
    """$GPGGA — 定位信息（时间、位置、质量、卫星数）"""
    raw: str = ""
    talker_id: str = "GP"
    line_number: int = 0
    utc_time: Optional[time] = None
    latitude: Optional[float] = None      # 十进制度
    lat_hemisphere: str = ""
    longitude: Optional[float] = None     # 十进制度
    lon_hemisphere: str = ""
    fix_quality: int = -1                  # 0=无效 1=单点 2=伪距差分 4=RTK固定解 5=RTK浮点解
    satellites: int = -1
    hdop: Optional[float] = None
    altitude: Optional[float] = None       # 海拔高度（米）
    alt_unit: str = "M"
    geoid_separation: Optional[float] = None  # 大地水准面差距
    geoid_unit: str = "M"
    dgps_age: Optional[float] = None       # 差分数据龄期（秒）
    dgps_station: Optional[str] = None     # 差分站ID
    checksum_valid: bool = False


@dataclass
class RMC:
    """$GPRMC — 推荐最小定位信息"""
    raw: str = ""
    talker_id: str = "GP"
    line_number: int = 0
    utc_time: Optional[time] = None
    status: str = ""                       # A=有效 V=无效
    latitude: Optional[float] = None
    lat_hemisphere: str = ""
    longitude: Optional[float] = None
    lon_hemisphere: str = ""
    speed_over_ground: Optional[float] = None  # 节
    track_angle: Optional[float] = None        # 度
    date: Optional[datetime] = None
    magnetic_variation: Optional[float] = None
    mag_var_direction: str = ""
    mode_indicator: str = ""                # A=自主 D=差分 E=估算 N=无效
    checksum_valid: bool = False


@dataclass
class GSA:
    """$GPGSA — 精度因子与活跃卫星"""
    raw: str = ""
    talker_id: str = "GP"
    line_number: int = 0
    mode1: str = ""                         # M=手动 A=自动
    mode2: int = -1                         # 1=无定位 2=2D 3=3D
    satellite_ids: list = field(default_factory=list)  # 最多12颗
    pdop: Optional[float] = None
    hdop: Optional[float] = None
    vdop: Optional[float] = None
    checksum_valid: bool = False


@dataclass
class GSV:
    """$GPGSV — 可见卫星信息"""
    raw: str = ""
    talker_id: str = "GP"
    line_number: int = 0
    total_messages: int = -1
    message_number: int = -1
    satellites_in_view: int = -1
    satellites: list = field(default_factory=list)  # [(prn, elevation, azimuth, snr), ...]
    checksum_valid: bool = False


@dataclass
class VTG:
    """$GPVTG — 对地航向与速度"""
    raw: str = ""
    talker_id: str = "GP"
    line_number: int = 0
    track_true: Optional[float] = None       # 真北航向（度）
    track_magnetic: Optional[float] = None   # 磁北航向（度）
    speed_knots: Optional[float] = None      # 速度（节）
    speed_kmh: Optional[float] = None        # 速度（公里/小时）
    mode_indicator: str = ""                 # A=自主 D=差分 E=估算 N=无效
    checksum_valid: bool = False


# ─── 工具函数 ──────────────────────────────────────────────


def _parse_lat_lon(value: str, direction: str) -> Optional[float]:
    """将 NMEA 经纬度（ddmm.mmmm）转为十进制度"""
    if not value or not direction:
        return None
    try:
        # 格式：ddmm.mmmm 或 dddmm.mmmm
        # 纬度前2位是度、经度前3位是度，但 int(value/100) 对两者均适用
        degrees = int(float(value) / 100)
        minutes = float(value) - degrees * 100
        decimal = degrees + minutes / 60.0
        if direction in ("S", "W"):
            decimal = -decimal
        return round(decimal, 8)
    except (ValueError, IndexError):
        return None


def _parse_utc_time(t_str: str) -> Optional[time]:
    """解析 UTC 时间字符串 hhmmss.ss"""
    if not t_str or len(t_str) < 6:
        return None
    try:
        h = int(t_str[0:2])
        m = int(t_str[2:4])
        sec_part = t_str[4:]  # "56.78" 或 "00.00"
        s = int(sec_part.split('.')[0])
        us = int((sec_part.split('.') + ['0'])[1].ljust(6, '0')[:6])
        return time(h, m, s, us)
    except (ValueError, IndexError):
        return None


def _parse_date(d_str: str) -> Optional[datetime]:
    """解析 UTC 日期字符串 ddmmyy"""
    if not d_str or len(d_str) != 6:
        return None
    try:
        d = int(d_str[0:2])
        m = int(d_str[2:4])
        y = int(d_str[4:6]) + 2000
        return datetime(y, m, d)
    except (ValueError, IndexError):
        return None


def checksum_verify(sentence: str) -> bool:
    """校验 NMEA 语句的 XOR 校验和"""
    if not sentence.startswith("$") or "*" not in sentence:
        return False
    # 去掉开头的 $ 和 * 后面的校验值
    body = sentence[1:sentence.index("*")]
    expected_checksum_str = sentence[sentence.index("*") + 1:].strip()
    try:
        expected = int(expected_checksum_str, 16)
    except ValueError:
        return False
    # 计算校验和：$ 和 * 之间所有字符的 XOR
    checksum = 0
    for char in body:
        checksum ^= ord(char)
    return checksum == expected


# ─── 解析函数 ──────────────────────────────────────────────


def parse_gga(fields: list, raw: str) -> GGA:
    """解析 $GPGGA 语句"""
    gga = GGA(raw=raw)
    if len(fields) < 14:
        raise NMEAParseError(f"GGA 字段不足：期望≥14，实际{len(fields)}")
    gga.talker_id = fields[0][:2] if len(fields[0]) >= 2 else "GP"
    gga.utc_time = _parse_utc_time(fields[1])
    gga.latitude = _parse_lat_lon(fields[2], fields[3])
    gga.lat_hemisphere = fields[3]
    gga.longitude = _parse_lat_lon(fields[4], fields[5])
    gga.lon_hemisphere = fields[5]
    gga.fix_quality = int(fields[6]) if fields[6].isdigit() else -1
    gga.satellites = int(fields[7]) if fields[7].isdigit() else -1
    gga.hdop = float(fields[8]) if fields[8] else None
    gga.altitude = float(fields[9]) if fields[9] else None
    gga.alt_unit = fields[10] if len(fields) > 10 else "M"
    gga.geoid_separation = float(fields[11]) if len(fields) > 11 and fields[11] else None
    gga.geoid_unit = fields[12] if len(fields) > 12 else "M"
    gga.dgps_age = float(fields[13]) if len(fields) > 13 and fields[13] else None
    gga.dgps_station = fields[14] if len(fields) > 14 else ""
    gga.checksum_valid = checksum_verify(raw)
    return gga


def parse_rmc(fields: list, raw: str) -> RMC:
    """解析 $GPRMC 语句"""
    rmc = RMC(raw=raw)
    if len(fields) < 11:
        raise NMEAParseError(f"RMC 字段不足：期望≥11，实际{len(fields)}")
    rmc.talker_id = fields[0][:2] if len(fields[0]) >= 2 else "GP"
    rmc.utc_time = _parse_utc_time(fields[1])
    rmc.status = fields[2]
    rmc.latitude = _parse_lat_lon(fields[3], fields[4])
    rmc.lat_hemisphere = fields[4]
    rmc.longitude = _parse_lat_lon(fields[5], fields[6])
    rmc.lon_hemisphere = fields[6]
    rmc.speed_over_ground = float(fields[7]) if fields[7] else None
    rmc.track_angle = float(fields[8]) if fields[8] else None
    rmc.date = _parse_date(fields[9]) if len(fields) > 9 else None
    rmc.magnetic_variation = float(fields[10]) if len(fields) > 10 and fields[10] else None
    rmc.mag_var_direction = fields[11] if len(fields) > 11 else ""
    rmc.mode_indicator = fields[12] if len(fields) > 12 else ""
    rmc.checksum_valid = checksum_verify(raw)
    return rmc


def parse_gsa(fields: list, raw: str) -> GSA:
    """解析 $GPGSA 语句"""
    gsa = GSA(raw=raw)
    if len(fields) < 17:
        raise NMEAParseError(f"GSA 字段不足：期望≥17，实际{len(fields)}")
    gsa.talker_id = fields[0][:2] if len(fields[0]) >= 2 else "GP"
    gsa.mode1 = fields[1]
    gsa.mode2 = int(fields[2]) if fields[2].isdigit() else -1
    gsa.satellite_ids = [int(f) for f in fields[3:15] if f]
    gsa.pdop = float(fields[15]) if fields[15] else None
    gsa.hdop = float(fields[16]) if fields[16] else None
    gsa.vdop = float(fields[17]) if len(fields) > 17 and fields[17] else None
    gsa.checksum_valid = checksum_verify(raw)
    return gsa


def parse_gsv(fields: list, raw: str) -> GSV:
    """解析 $GPGSV 语句"""
    gsv = GSV(raw=raw)
    if len(fields) < 4:
        raise NMEAParseError(f"GSV 字段不足：期望≥4，实际{len(fields)}")
    gsv.talker_id = fields[0][:2] if len(fields[0]) >= 2 else "GP"
    gsv.total_messages = int(fields[1]) if fields[1].isdigit() else -1
    gsv.message_number = int(fields[2]) if fields[2].isdigit() else -1
    gsv.satellites_in_view = int(fields[3]) if fields[3].isdigit() else -1
    # 每4个字段一组表示一颗卫星
    for i in range(4, len(fields) - 1, 4):
        if i + 3 >= len(fields):
            break
        try:
            prn = int(fields[i]) if fields[i] else 0
            elev = int(fields[i+1]) if fields[i+1] else 0
            azim = int(fields[i+2]) if fields[i+2] else 0
            snr = int(fields[i+3]) if fields[i+3] else 0
            gsv.satellites.append({
                "prn": prn, "elevation": elev,
                "azimuth": azim, "snr": snr
            })
        except (ValueError, IndexError):
            break
    gsv.checksum_valid = checksum_verify(raw)
    return gsv


def parse_vtg(fields: list, raw: str) -> VTG:
    """解析 $GPVTG 语句"""
    vtg = VTG(raw=raw)
    if len(fields) < 8:
        raise NMEAParseError(f"VTG 字段不足：期望≥8，实际{len(fields)}")
    vtg.talker_id = fields[0][:2] if len(fields[0]) >= 2 else "GP"
    vtg.track_true = float(fields[1]) if fields[1] else None
    vtg.track_magnetic = float(fields[3]) if len(fields) > 3 and fields[3] else None
    vtg.speed_knots = float(fields[5]) if len(fields) > 5 and fields[5] else None
    vtg.speed_kmh = float(fields[7]) if len(fields) > 7 and fields[7] else None
    vtg.mode_indicator = fields[9] if len(fields) > 9 else ""
    vtg.checksum_valid = checksum_verify(raw)
    return vtg


# ─── 总入口 ────────────────────────────────────────────────


SENTENCE_PARSERS = {
    "GGA": parse_gga,
    "RMC": parse_rmc,
    "GSA": parse_gsa,
    "GSV": parse_gsv,
    "VTG": parse_vtg,
}


def parse_sentence(sentence: str):
    """
    解析单条 NMEA 语句，自动识别类型

    返回: (sentence_type, data_object) 或 (None, None)
    """
    sentence = sentence.strip()
    if not sentence.startswith("$"):
        return None, None

    # 提取 talker_id + sentence_type  → "GPGGA" → "GGA"
    if "*" in sentence:
        body = sentence[1:sentence.index("*")]
    else:
        body = sentence[1:]

    parts = body.split(",")
    if not parts[0]:
        return None, None

    full_type = parts[0]  # 例如 "GPGGA" 或 "GNGGA"
    # 取后3位作为语句类型
    sentence_type = full_type[-3:] if len(full_type) >= 3 else full_type

    parser = SENTENCE_PARSERS.get(sentence_type)
    if parser is None:
        return sentence_type, None  # 未知类型

    try:
        return sentence_type, parser(parts, sentence)
    except (NMEAParseError, ValueError, IndexError) as e:
        return sentence_type, str(e)


def parse_file(filepath: str):
    """
    解析整个 NMEA 日志文件

    返回: (by_talker_type, epochs, errors)
      - by_talker_type: {"GPGGA": [GGA, ...], "GNGGA": [...], ...}
          按 talker_id + 语句类型分组，多星座不并桶
      - epochs: {"083000": [GGA, RMC, GSA, ...], "083001": [...], ...}
          按 UTC 时间戳将同一秒的语句聚成一个历元；
          无时间戳的语句（GSA/GSV/VTG）归入最近一次 GGA/RMC 所在历元
      - errors: ["第N行: 错误描述", ...]
    """
    by_type = {}
    epochs = {}
    errors = []
    current_epoch = None

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or not line.startswith("$"):
                continue
            stype, data = parse_sentence(line)
            if data is None and stype:
                errors.append(f"第{line_num}行: 无法解析 {stype}")
            elif isinstance(data, str):
                errors.append(f"第{line_num}行: {data}")
            else:
                # 记录文件行号
                data.line_number = line_num

                # 按 talker+type 分组（如 "GPGGA" / "GNGGA"）
                key = f"{data.talker_id}{stype}"
                by_type.setdefault(key, []).append(data)

                # 更新当前历元（GGA/RMC 带有时间戳）
                if stype in ("GGA", "RMC") and data.utc_time is not None:
                    current_epoch = data.utc_time.strftime("%H%M%S.%f")

                # 归入历元
                if current_epoch is not None:
                    epochs.setdefault(current_epoch, []).append(data)

    return by_type, epochs, errors
