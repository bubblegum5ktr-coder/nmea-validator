# NMEA 日志解析 & 校验工具

针对 GNSS/RTK 设备 NMEA-0183 输出日志的解析和自动化校验工具。

## 背景

中海达的 RTK 接收机 / GNSS 接收机板卡通过串口/TCP 输出 NMEA-0183 格式的定位数据。测试工程师需要：
- 看懂原始 NMEA 数据，确认设备输出正确
- 自动校验定位质量、坐标范围、差分状态
- 批量跑历史日志，快速定位问题数据

这个工具就是干这个的。

## 支持的 NMEA 语句

| 语句 | 含义 | 关键字段 |
|------|------|---------|
| GGA | 定位信息 | 时间、坐标、定位质量、卫星数、HDOP、高程 |
| RMC | 推荐最小定位信息 | 时间、坐标、速度、航向、日期 |
| GSA | 精度因子 | PDOP、HDOP、VDOP、活跃卫星列表 |
| GSV | 可见卫星 | 卫星号、仰角、方位角、信噪比 |
| VTG | 对地航向与速度 | 真北航向、速度（节/km/h） |

## 快速开始

```bash
# 1. 演示脚本 — 逐步展示解析和校验过程
python -X utf8 demo.py

# 2. 跑测试 — 验证功能正确性
python -m pytest test_nmea.py -v

# 3. 解析自己的日志文件
python -c "from nmea_validator import validate_file; print(validate_file('你的日志.nmea').summary())"
```

## 项目结构

```
nmea-validator/
├── nmea_parser.py       # 核心：NMEA 语句解析
├── nmea_validator.py    # 核心：定位数据校验规则
├── test_nmea.py         # pytest 测试套件（67 条）
├── demo.py              # 逐步演示脚本
├── NMEA入门-从测量员到测试工程师.md  # 概念学习文档
├── samples/
│   └── sample_1.nmea    # 示例 NMEA 日志（含正常+异常场景）
├── reports/             # 测试报告输出目录
├── .gitignore
└── README.md
```

## 校验规则

工具校验分**两级**——语句级和历元级（按严重程度分 error/warning/info）：

**语句级**（逐条检查）：
- **error**: 校验和失败、经纬度超出范围、DOP 异常、卫星数异常
- **warning**: 定位无效/浮点解、差分龄期过长、信号弱、HDOP偏高
- **info**: 定位质量等级、卫星未跟踪、仰角过低

**历元级**（同一时间戳的一组语句）：
- **error**: 同一精确时刻出现多条 GGA/RMC/VTG（数据错乱/串扰）
- GSA/GSV 同一历元允许多条（多星座分系统 + GSV 续号，属正常）

**历元 key 带小数秒**（`083000.200000`），5Hz/10Hz 等高频接收机每秒多次定位各自独立成历元，不会误报。

## 学习路径

1. 先跑 `demo.py`，看懂每条语句长什么样
2. 改 `samples/sample_1.nmea` 加入自己的测试数据
3. 读 `nmea_validator.py` 里的校验规则，看每个规则对应实际什么场景
4. 跑 `test_nmea.py`，理解 pytest 参数化测试的写法
