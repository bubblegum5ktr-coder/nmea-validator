# NMEA 日志解析 & 校验工具

针对 GNSS/RTK 设备 NMEA-0183 输出日志的解析和自动化校验工具。适用于中海达 RTK 接收机等设备的测试场景。

> A parsing and validation tool for NMEA-0183 logs from GNSS/RTK devices. Designed for testing Hi-Target RTK receivers and similar equipment.

## 背景 / Background

中海达的 RTK 接收机 / GNSS 接收机板卡通过串口/TCP 输出 NMEA-0183 格式的定位数据。测试工程师需要：
- 看懂原始 NMEA 数据，确认设备输出正确
- 自动校验定位质量、坐标范围、差分状态
- 批量跑历史日志，快速定位问题数据

> Hi-Target RTK/GNSS receivers output NMEA-0183 positioning data via serial/TCP. QA engineers need to parse raw logs, validate fix quality & coordinate ranges, and batch-process historical logs to quickly identify anomalies.

## 支持的 NMEA 语句 / Supported Sentences

| Sentence | Meaning | Key Fields |
|----------|---------|------------|
| GGA | 定位信息 / Fix data | 时间、坐标、定位质量、卫星数、HDOP、高程 / Time, coordinates, fix quality, satellites, HDOP, altitude |
| RMC | 推荐最小定位信息 / Recommended minimum | 时间、坐标、速度、航向、日期 / Time, coordinates, speed, course, date |
| GSA | 精度因子 / DOP & active satellites | PDOP、HDOP、VDOP、活跃卫星列表 / PDOP, HDOP, VDOP, active satellite IDs |
| GSV | 可见卫星 / Satellites in view | 卫星号、仰角、方位角、信噪比 / PRN, elevation, azimuth, SNR |
| VTG | 对地航向与速度 / Course & speed | 真北航向、速度（节/km/h）/ True course, speed (knots/km/h) |

## 快速开始 / Quick Start

```bash
# 1. 演示脚本 / Demo — step-by-step parsing walkthrough
python -X utf8 demo.py

# 2. 跑测试 / Run tests
python -m pytest test_nmea.py -v

# 3. 解析自己的日志文件 / Parse your own log
python -c "from nmea_validator import validate_file; print(validate_file('your_log.nmea').summary())"
```

## 项目结构 / Project Structure

```
nmea-validator/
├── nmea_parser.py       ← 核心：NMEA 语句解析 / Sentence parser
├── nmea_validator.py    ← 核心：定位数据校验规则 / Validation rules
├── test_nmea.py         ← pytest 测试套件 / Test suite (67 tests)
├── demo.py              ← 逐步演示脚本 / Step-by-step demo
├── NMEA入门-从测量员到测试工程师.md  ← 概念学习文档 / Learning guide (CN)
├── samples/
│   └── sample_1.nmea    ← 示例 NMEA 日志 / Sample log (normal + edge cases)
└── reports/             ← 测试报告输出 / Test report output
```

## 校验规则 / Validation Rules

工具校验分**两级**——语句级和历元级（按严重程度分 error/warning/info）：

> Two-level validation: sentence-level and epoch-level, with three severity levels: error, warning, info.

**语句级 / Sentence-level** (逐条检查 / per-sentence check):
- **error**: 校验和失败 / Checksum failure, 经纬度超出范围 / Lat/Lon out of range, DOP 异常 / abnormal DOP, 卫星数异常 / invalid satellite count
- **warning**: 定位无效/浮点解 / Invalid or float fix, 差分龄期过长 / DGPS age too long, 信号弱 / weak signal, HDOP偏高 / high HDOP
- **info**: 定位质量等级 / Fix quality level, 卫星未跟踪 / satellite not tracked, 仰角过低 / low elevation

**历元级 / Epoch-level** (同一时间戳的一组语句 / sentences sharing a timestamp):
- **error**: 同一精确时刻出现多条 GGA/RMC/VTG（数据错乱/串扰）/ Multiple GGA/RMC/VTG in same exact moment
- GSA/GSV 同一历元允许多条（多星座分系统 + GSV 续号，属正常）/ Multiple GSA/GSV per epoch is normal (multi-constellation + GSV pagination)

**历元 key 带小数秒**（`083000.200000`），5Hz/10Hz 等高频接收机每秒多次定位各自独立成历元，不会误报。

> Epoch key includes fractional seconds. 5Hz/10Hz high-frequency receivers produce multiple independent epochs per second — no false positives.

## 学习路径 / Learning Path

1. 先跑 `demo.py`，看懂每条语句长什么样 / Run demo.py to see what each sentence looks like
2. 改 `samples/sample_1.nmea` 加入自己的测试数据 / Add your own test data
3. 读 `nmea_validator.py` 里的校验规则，看每个规则对应实际什么场景 / Read the validation rules
4. 跑 `test_nmea.py`，理解 pytest 参数化测试的写法 / Run tests, learn pytest parametrization

## 技术栈 / Tech Stack

- **Python 3** — 核心语言
- **pytest** — 测试框架（67 条用例 / 67 test cases）
- **NMEA-0183** — GNSS 标准协议 / Standard GNSS protocol
