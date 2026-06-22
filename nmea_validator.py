"""
NMEA 数据校验器
针对测绘/GNSS 实际场景，验证定位数据的合理性和完整性
"""

from typing import List, Optional
from dataclasses import dataclass, field

from nmea_parser import GGA, RMC, GSA, GSV, VTG, parse_file


@dataclass
class ValidationResult:
    """单条校验结果"""
    line_number: int = 0             # 文件行号
    sentence_type: str = ""          # 语句类型（GGA/RMC/...）
    level: str = "info"              # info / warning / error
    message: str = ""
    raw: str = ""

    @property
    def index(self):
        """向后兼容旧代码引用 .index"""
        return self.line_number


@dataclass
class ValidationReport:
    """完整校验报告"""
    file_path: str = ""
    total_sentences: int = 0
    results: List[ValidationResult] = field(default_factory=list)

    @property
    def errors(self):
        return [r for r in self.results if r.level == "error"]

    @property
    def warnings(self):
        return [r for r in self.results if r.level == "warning"]

    @property
    def infos(self):
        return [r for r in self.results if r.level == "info"]

    def summary(self) -> str:
        lines = [
            f"校验文件: {self.file_path}",
            f"总语句数: {self.total_sentences}",
            f"错误: {len(self.errors)}  警告: {len(self.warnings)}  信息: {len(self.infos)}",
        ]
        if self.errors:
            lines.append(f"\n⚠ 错误详情:")
            for r in self.errors:
                loc = f"行{r.line_number}" if r.line_number else ""
                lines.append(f"  [{r.sentence_type} {loc}] {r.message}")
        if self.warnings:
            lines.append(f"\n⚡ 警告详情:")
            for r in self.warnings:
                loc = f"行{r.line_number}" if r.line_number else ""
                lines.append(f"  [{r.sentence_type} {loc}] {r.message}")
        return "\n".join(lines)


def _check_gga(gga: GGA, idx: int) -> List[ValidationResult]:
    """校验 GGA 定位信息"""
    results = []

    # 1. 校验和
    if not gga.checksum_valid:
        results.append(ValidationResult(idx, "GGA", "error", "校验和失败，数据可能损坏"))

    # 2. 定位质量
    if gga.fix_quality == 0:
        results.append(ValidationResult(idx, "GGA", "warning", f"定位无效（fix_quality=0），解状态: 未定位"))
    elif gga.fix_quality == 1:
        results.append(ValidationResult(idx, "GGA", "info", f"单点定位（fix_quality=1），精度约3-10米"))
    elif gga.fix_quality == 2:
        results.append(ValidationResult(idx, "GGA", "info", f"伪距差分（fix_quality=2），精度亚米级"))
    elif gga.fix_quality == 4:
        results.append(ValidationResult(idx, "GGA", "info", f"RTK 固定解（fix_quality=4），精度厘米级 ✓"))
    elif gga.fix_quality == 5:
        results.append(ValidationResult(idx, "GGA", "warning", f"RTK 浮点解（fix_quality=5），精度分米级"))
    elif gga.fix_quality == -1:
        results.append(ValidationResult(idx, "GGA", "error", "无法解析 fix_quality"))

    # 3. 经纬度范围
    if gga.latitude is not None:
        if abs(gga.latitude) > 90:
            results.append(ValidationResult(idx, "GGA", "error", f"纬度异常: {gga.latitude}°（超出±90°）"))
    else:
        results.append(ValidationResult(idx, "GGA", "warning", "纬度为空"))

    if gga.longitude is not None:
        if abs(gga.longitude) > 180:
            results.append(ValidationResult(idx, "GGA", "error", f"经度异常: {gga.longitude}°（超出±180°）"))
    else:
        results.append(ValidationResult(idx, "GGA", "warning", "经度为空"))

    # 4. 卫星数与定位状态一致性
    if gga.fix_quality > 0 and gga.satellites == 0:
        results.append(ValidationResult(idx, "GGA", "warning", f"有定位解但卫星数为0（逻辑不一致）"))
    if gga.fix_quality == 4 and gga.satellites < 4:
        results.append(ValidationResult(idx, "GGA", "warning", f"RTK 固定解通常需≥4颗卫星，当前{gga.satellites}颗"))
    if gga.satellites > 50:
        results.append(ValidationResult(idx, "GGA", "error", f"卫星数异常: {gga.satellites}（GNSS系统理论最多~140，单系统最多~36）"))

    # 5. HDOP（水平精度因子，越小越好）
    if gga.hdop is not None:
        if gga.hdop <= 0:
            results.append(ValidationResult(idx, "GGA", "warning", f"HDOP异常: {gga.hdop}（应为正值）"))
        elif gga.hdop < 0.5:
            results.append(ValidationResult(idx, "GGA", "info", f"HDOP={gga.hdop}，水平精度极优"))
        elif gga.hdop < 2.0:
            results.append(ValidationResult(idx, "GGA", "info", f"HDOP={gga.hdop}，水平精度良好"))
        elif gga.hdop > 5:
            results.append(ValidationResult(idx, "GGA", "warning", f"HDOP={gga.hdop}，水平精度较差（>5）"))

    # 6. 海拔高度
    if gga.altitude is not None:
        if gga.altitude < -500 or gga.altitude > 9000:
            results.append(ValidationResult(idx, "GGA", "error", f"海拔异常: {gga.altitude}m（合理范围-500~9000m）"))

    # 7. 差分龄期（RTK 场景下太久说明差分信号断过）
    if gga.dgps_age is not None and gga.dgps_age > 10:
        results.append(ValidationResult(idx, "GGA", "warning", f"差分龄期: {gga.dgps_age}s（>10s，差分信号可能中断过）"))

    return results


def _check_rmc(rmc: RMC, idx: int) -> List[ValidationResult]:
    """校验 RMC 推荐最小定位信息"""
    results = []

    if not rmc.checksum_valid:
        results.append(ValidationResult(idx, "RMC", "error", "校验和失败"))

    # 状态
    if rmc.status == "V":
        results.append(ValidationResult(idx, "RMC", "warning", "导航状态无效（status=V）"))
    elif not rmc.status:
        results.append(ValidationResult(idx, "RMC", "error", "状态字段为空"))
    elif rmc.status != "A":
        results.append(ValidationResult(idx, "RMC", "warning", f"未知状态标志: {rmc.status}"))

    # 经纬度（同 GGA 逻辑）
    if rmc.latitude is not None and abs(rmc.latitude) > 90:
        results.append(ValidationResult(idx, "RMC", "error", f"纬度异常: {rmc.latitude}°"))
    if rmc.longitude is not None and abs(rmc.longitude) > 180:
        results.append(ValidationResult(idx, "RMC", "error", f"经度异常: {rmc.longitude}°"))

    # 速度
    if rmc.speed_over_ground is not None:
        if rmc.speed_over_ground < 0:
            results.append(ValidationResult(idx, "RMC", "error", f"速度为负: {rmc.speed_over_ground} 节"))
        elif rmc.speed_over_ground > 500:
            results.append(ValidationResult(idx, "RMC", "warning", f"速度异常偏高: {rmc.speed_over_ground} 节（约{rmc.speed_over_ground*1.852:.0f}km/h）"))

    # 航向
    if rmc.track_angle is not None and (rmc.track_angle < 0 or rmc.track_angle > 360):
        results.append(ValidationResult(idx, "RMC", "error", f"航向异常: {rmc.track_angle}°（应在0~360）"))

    return results


def _check_gsa(gsa: GSA, idx: int) -> List[ValidationResult]:
    """校验 GSA 精度因子"""
    results = []

    if not gsa.checksum_valid:
        results.append(ValidationResult(idx, "GSA", "error", "校验和失败"))

    # DOP 值
    if gsa.pdop is not None:
        if gsa.pdop < 0:
            results.append(ValidationResult(idx, "GSA", "error", f"PDOP异常: {gsa.pdop}"))
        elif gsa.pdop > 10:
            results.append(ValidationResult(idx, "GSA", "warning", f"PDOP={gsa.pdop}（>10，几何分布很差）"))
    if gsa.hdop is not None and gsa.hdop < 0:
        results.append(ValidationResult(idx, "GSA", "error", f"HDOP异常: {gsa.hdop}"))
    if gsa.vdop is not None:
        if gsa.vdop < 0:
            results.append(ValidationResult(idx, "GSA", "error", f"VDOP异常: {gsa.vdop}"))
        elif gsa.vdop > 10:
            results.append(ValidationResult(idx, "GSA", "warning", f"VDOP={gsa.vdop}（>10，高程精度较差）"))

    # 模式
    if gsa.mode2 == 1:
        results.append(ValidationResult(idx, "GSA", "info", "定位模式: 无定位"))
    elif gsa.mode2 == 2:
        results.append(ValidationResult(idx, "GSA", "info", "定位模式: 2D"))
    elif gsa.mode2 == 3:
        pass  # 3D 正常
    else:
        results.append(ValidationResult(idx, "GSA", "warning", f"未知定位模式: {gsa.mode2}"))

    return results


def _check_gsv(gsv: GSV, idx: int) -> List[ValidationResult]:
    """校验 GSV 可见卫星"""
    results = []

    if not gsv.checksum_valid:
        results.append(ValidationResult(idx, "GSV", "error", "校验和失败"))

    # 卫星信噪比
    for sat in gsv.satellites:
        if sat["snr"] == 0:
            results.append(ValidationResult(idx, "GSV", "info", f"卫星 PRN{sat['prn']} 未跟踪到信号（SNR=0）"))
        elif sat["snr"] < 30:
            results.append(ValidationResult(idx, "GSV", "warning", f"卫星 PRN{sat['prn']} 信号弱（SNR={sat['snr']}，<30）"))
        if sat["elevation"] < 10:
            results.append(ValidationResult(idx, "GSV", "info", f"卫星 PRN{sat['prn']} 仰角过低（{sat['elevation']}°，<10°）"))

    return results


def _check_vtg(vtg: VTG, idx: int) -> List[ValidationResult]:
    """校验 VTG 航向速度"""
    results = []

    if not vtg.checksum_valid:
        results.append(ValidationResult(idx, "VTG", "error", "校验和失败"))

    if vtg.track_true is not None and (vtg.track_true < 0 or vtg.track_true > 360):
        results.append(ValidationResult(idx, "VTG", "error", f"真北航向异常: {vtg.track_true}°"))
    if vtg.speed_kmh is not None and vtg.speed_kmh > 300:
        results.append(ValidationResult(idx, "VTG", "warning", f"地速异常偏高: {vtg.speed_kmh}km/h"))

    return results


CHECKERS = {
    "GGA": _check_gga,
    "RMC": _check_rmc,
    "GSA": _check_gsa,
    "GSV": _check_gsv,
    "VTG": _check_vtg,
}

# 每历元应唯一的语句类型（GSA/GSV 不在此列）
_UNIQUE_PER_EPOCH = {"GGA", "RMC", "VTG"}

# 用于从对象判断语句类型
_SENTENCE_CLASS_TO_TYPE = {
    GGA: "GGA", RMC: "RMC", GSA: "GSA", GSV: "GSV", VTG: "VTG",
}


def _sentence_type(obj) -> str:
    """返回对象的语句类型字符串"""
    return _SENTENCE_CLASS_TO_TYPE.get(type(obj), "")


def _check_epoch_duplicates(sentences: list, epoch_key: str) -> List[ValidationResult]:
    """
    校验同一历元内唯一性：
    GGA / RMC / VTG 每历元应只有一条；
    GSA / GSV 允许出现多条（多星座 + GSV 续号），不报错。
    """
    # 展示用的历元标识：截断到厘秒（2 位小数），去掉无意义的尾随零
    display_key = epoch_key
    if "." in epoch_key:
        hhmmss, frac = epoch_key.split(".")
        # 保留前 2 位小数（厘秒），去掉尾随零
        short_frac = frac[:2].rstrip("0") or "0"
        display_key = f"{hhmmss}.{short_frac}"

    results = []
    for stype in _UNIQUE_PER_EPOCH:
        matches = [s for s in sentences if _sentence_type(s) == stype]
        if len(matches) > 1:
            line_nums = [s.line_number for s in matches]
            results.append(ValidationResult(
                line_number=min(line_nums),
                sentence_type=stype,
                level="error",
                message=(
                    f"历元 {display_key} 内出现 {len(matches)} 条 {stype}"
                    f"（应唯一），涉及行: {line_nums}"
                ),
            ))
    return results


def validate_file(filepath: str) -> ValidationReport:
    """
    校验整个 NMEA 日志文件

    返回 ValidationReport 包含所有校验结果
    """
    by_type, epochs, parse_errors = parse_file(filepath)
    report = ValidationReport(file_path=filepath)

    # 统计总语句数
    for key, sentences in by_type.items():
        report.total_sentences += len(sentences)

    # 解析错误
    for err in parse_errors:
        report.results.append(ValidationResult(sentence_type="", level="error", message=err))

    # 逐语句校验
    for key, sentences in by_type.items():
        stype = key[-3:] if len(key) >= 3 else key  # "GPGGA" → "GGA"
        checker = CHECKERS.get(stype)
        if checker is None:
            continue
        for sentence in sentences:
            ln = getattr(sentence, "line_number", 0)
            report.results.extend(checker(sentence, ln))

    # 历元级校验：检查 GGA/RMC/VTG 是否每历元唯一
    for epoch_key, sentences in epochs.items():
        report.results.extend(_check_epoch_duplicates(sentences, epoch_key))

    return report


def validate_data(by_type: dict, epochs: dict = None) -> ValidationReport:
    """直接对已解析的数据进行校验（不读文件）"""
    report = ValidationReport(file_path="<memory>")

    for key, sentences in by_type.items():
        stype = key[-3:] if len(key) >= 3 else key
        checker = CHECKERS.get(stype)
        if checker is None:
            continue
        for sentence in sentences:
            ln = getattr(sentence, "line_number", 0)
            report.total_sentences += 1
            report.results.extend(checker(sentence, ln))

    if epochs:
        for epoch_key, sentences in epochs.items():
            report.results.extend(_check_epoch_duplicates(sentences, epoch_key))

    return report
