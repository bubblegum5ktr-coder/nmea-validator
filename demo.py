"""
NMEA 日志解析 & 校验 — 演示脚本
逐步展示：读取 → 解析 → 校验 → 报告，适合边看边学
"""

import sys
from pathlib import Path

# 脚本所在目录加到 sys.path，方便直接跑
sys.path.insert(0, str(Path(__file__).parent))

from nmea_parser import parse_sentence, parse_file, GGA, RMC, GSA, GSV, VTG
from nmea_validator import validate_file


def _stype(obj):
    """返回语句对象对应的类型缩写"""
    m = {GGA: "GGA", RMC: "RMC", GSA: "GSA", GSV: "GSV", VTG: "VTG"}
    return m.get(type(obj), "?")


def banner(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def demo_single_sentence():
    """单条 NMEA 语句解析演示"""
    banner("1. 单条语句解析")

    # 一条典型的 RTK 固定解 GGA 语句
    raw = "$GPGGA,083000.00,2308.12345,N,11322.56789,E,4,12,0.8,15.3,M,-5.2,M,1.5,0001*61"

    print(f"原始 NMEA 语句:")
    print(f"  {raw}\n")

    stype, result = parse_sentence(raw)
    print(f"类型: {stype}")
    print(f"解析结果:")
    print(f"  时间 (UTC):     {result.utc_time}")
    print(f"  纬度:           {result.latitude}° {result.lat_hemisphere}")
    print(f"  经度:           {result.longitude}° {result.lon_hemisphere}")
    print(f"  定位质量:       {result.fix_quality} → {'RTK 固定解 ✓' if result.fix_quality == 4 else '其他'}")
    print(f"  卫星数:         {result.satellites} 颗")
    print(f"  HDOP:           {result.hdop}（<1.0，精度极好）")
    print(f"  海拔:           {result.altitude}m")
    print(f"  大地水准面差距: {result.geoid_separation}m")
    print(f"  差分龄期:       {result.dgps_age}s")
    print(f"  校验和:         {'✓ 通过' if result.checksum_valid else '✗ 失败'}")


def demo_field_explanation():
    """解释 GGA 语句每个字段的含义"""
    banner("2. GGA 字段逐位解释")

    raw = "$GPGGA,083000.00,2308.12345,N,11322.56789,E,4,12,0.8,15.3,M,-5.2,M,1.5,0001*61"
    # 去头去尾
    body = raw[1:raw.index("*")]
    fields = body.split(",")

    labels = [
        ("$GPGGA",      "语句头：$=开始，GP=GPS系统，GGA=定位信息"),
        ("083000.00",   "UTC时间：08:30:00.00"),
        ("2308.12345",  "纬度（ddmm.mmmm格式）：23°08.12345' N"),
        ("N",           "北纬"),
        ("11322.56789", "经度（dddmm.mmmm格式）：113°22.56789' E"),
        ("E",           "东经"),
        ("4",           "GPS质量：0=无效 1=单点 2=伪距差分 4=RTK固定 5=RTK浮点"),
        ("12",          "正在使用的卫星数"),
        ("0.8",         "水平精度因子 HDOP（越小越好，<1 极好）"),
        ("15.3",        "天线海拔高度（米）"),
        ("M",           "高度单位：米"),
        ("-5.2",        "大地水准面差距（WGS84椭球与平均海平面差）"),
        ("M",           "差距单位：米"),
        ("1.5",         "差分数据龄期（秒），距上次收到差分的间隔"),
        ("0001",        "差分参考站ID"),
        ("*61",         "校验和（$和*之间所有字节的XOR值，十六进制）"),
    ]

    for i, (value, desc) in enumerate(labels):
        print(f"  字段{i}: {value:<18} → {desc}")


def demo_parse_file():
    """解析整个 NMEA 日志文件"""
    banner("3. 解析整个日志文件")

    sample_file = Path(__file__).parent / "samples" / "sample_1.nmea"
    print(f"文件: {sample_file}\n")

    by_type, epochs, errors = parse_file(str(sample_file))

    if errors:
        print("❌ 解析错误:")
        for e in errors:
            print(f"  {e}")

    for key, sentences in sorted(by_type.items()):
        stype = key[-3:]  # 语句类型
        talker = key[:2]  # 星座
        if sentences:
            print(f"\n📡 {key} ({talker}系统/{stype}): {len(sentences)} 条")
            if stype == "GGA" and sentences:
                gga = sentences[0]
                print(f"   第1条 → 行{gga.line_number} 时间:{gga.utc_time} "
                      f"坐标:({gga.latitude}, {gga.longitude}) "
                      f"质量:{gga.fix_quality} 卫星:{gga.satellites} HDOP:{gga.hdop}")
            elif stype == "RMC" and sentences:
                rmc = sentences[0]
                print(f"   第1条 → 行{rmc.line_number} 时间:{rmc.utc_time} "
                      f"状态:{rmc.status} 速度:{rmc.speed_over_ground}节 "
                      f"航向:{rmc.track_angle}°")
            elif stype == "GSA" and sentences:
                gsa = sentences[0]
                print(f"   第1条 → 行{gsa.line_number} 模式:{gsa.mode2}D "
                      f"PDOP:{gsa.pdop} HDOP:{gsa.hdop} VDOP:{gsa.vdop}")
            elif stype == "GSV" and sentences:
                total_sats = sum(len(gsv.satellites) for gsv in sentences)
                print(f"   {len(sentences)} 条语句，共追踪 {total_sats} 颗卫星")
            elif stype == "VTG" and sentences:
                vtg = sentences[0]
                print(f"   第1条 → 行{vtg.line_number} 航向:{vtg.track_true}° "
                      f"速度:{vtg.speed_kmh}km/h")

    # 历元概览
    print(f"\n📊 历元数: {len(epochs)}")
    for epoch_key in sorted(epochs)[:5]:
        sentences = epochs[epoch_key]
        types = [_stype(s) for s in sentences]
        print(f"   历元 {epoch_key}: {len(sentences)} 条 → {types}")


def demo_validate():
    """校验演示 — 这里能找到哪些问题"""
    banner("4. 数据校验报告")

    sample_file = Path(__file__).parent / "samples" / "sample_1.nmea"
    report = validate_file(str(sample_file))

    print(report.summary())

    if report.results:
        print(f"\n── 所有校验结果（按级别排列）──")
        for level in ["error", "warning", "info"]:
            items = [r for r in report.results if r.level == level]
            if not items:
                continue
            emoji = {"error": "❌", "warning": "⚡", "info": "ℹ️"}[level]
            print(f"\n{emoji} {level.upper()} ({len(items)}条)")
            for r in items[:8]:  # 只展示前8条避免刷屏
                print(f"  [{r.sentence_type}#{r.index}] {r.message}")
            if len(items) > 8:
                print(f"  ... 还有 {len(items) - 8} 条")


def demo_what_this_means():
    """解释这些校验结果在实际工作中意味着什么"""
    banner("5. 校验结果 → 实际含义")

    issues = [
        ("fix_quality=0", "设备未定位 — 可能天线被遮挡、刚开机还在搜星"),
        ("校验和失败", "数据传输中损坏 — 检查线缆或无线传输质量"),
        ("RTK 浮点解", "差分信号在，但还不够稳定到固定 — 等几秒看能否固定"),
        ("HDOP>5", "卫星几何分布差 — 可能在峡谷/高楼区，换开阔处"),
        ("差分龄期>10s", "差分信号断过 — 检查数据链路（电台/网络）"),
        ("卫星数突然下降", "可能天线被遮挡或设备异常"),
        ("经纬度超出范围", "数据解析错误或设备固件 bug — 直接提缺陷单"),
        ("SNR过低", "该卫星信号弱 — 正常现象，但大片 SNR 低说明环境差"),
    ]

    for problem, meaning in issues:
        print(f"  发现 '{problem}'  →  {meaning}")


def main():
    banner("NMEA 日志解析 & 校验 演示")
    print("  中海达 RTK 测试必备技能：看懂设备输出的原始 NMEA 数据")

    demo_single_sentence()
    demo_field_explanation()
    demo_parse_file()
    demo_validate()
    demo_what_this_means()

    print(f"\n{'='*60}")
    print("  演示完成。接下来可以:")
    print("  1. 改 samples/sample_1.nmea 加自己的数据")
    print("  2. 跑 pytest test_nmea.py -v 看测试用例")
    print("  3. 用 python nmea_parser.py 解析自己的日志")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
