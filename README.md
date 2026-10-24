# STM32 BMS Virtual Testbench & Telemetry Gateway

A robust, production-grade Battery Management System (BMS) virtual testbench designed to bridge embedded firmware logic with a Python-based industrial monitoring GUI. This project emphasizes high-reliability communication protocols, physical-layer diagnostic readiness (CAN Bus & UART), and efficient state-machine telemetry parsing.

---

## 🚀 Key Features

* **Advanced CAN Bus Integration**: Implements Extended Frame (`CAN_ID_EXT`) protocol parsing, handling continuous active reporting (`0xFFFF`) and optimized memory mapping for 32 series cell voltages (`0x11110102 ~ 0x11110109`).
* **Strict Binary Framing & Packing**: Utilizes `#pragma pack(1)` memory alignment in C firmware to ensure zero-padding binary serialization, paired with a robust dual-byte header (`0xAA 0x55`) and checksum validation for reliable serial telemetry transmission.
* **Comprehensive Protection State Machine**: Real-time evaluation of multi-level battery protection triggers (Cell Over/Under-Voltage, Charge/Discharge Overcurrent, and Self-Lock Switch monitoring via 16-bit status words).
* **Multi-Threaded Python PyQt5 GUI**: Decouples serial reading and UI rendering to prevent UI freezing, featuring dynamic status indicators, cell voltage grids, and live logging.

---

## 📂 Project Architecture

```text
/
├── main.c                  # STM32 core firmware (CAN parsing, protection logic, binary packing)
├── bms_protocol.h          # Protocol definitions, data structures, and status word masks
└── bms_industrial_gui.py   # Python PyQt5 multi-threaded monitoring interface

## 🖥️ System Demonstration

**1. Normal Operation State (正常运行状态)**
* 实时监控 32 串单体电压、温度及 SOC 曲线。
* 系统运行平稳，所有状态指示灯正常。

![Normal State]<img width="1360" height="1111" alt="正常" src="https://github.com/user-attachments/assets/74a8ad34-373d-4f24-87fa-d984f6c89c15" />


**2. Fault Protection State (故障报警状态)**
* 模拟触发单体过压/欠压或过流保护时，状态机通过状态字位运算实时捕捉异常。
* 界面触发保护警告，MOS 状态与保护指示灯实时联动翻转。

![Fault State]<img width="1360" height="1111" alt="异常" src="https://github.com/user-attachments/assets/46dfc2fa-8e90-4af5-bd1d-1cb47f22a6c0" />

