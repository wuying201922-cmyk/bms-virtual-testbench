# STM32 BMS Virtual Testbench & Telemetry Gateway

A robust, production-grade Battery Management System (BMS) virtual testbench designed to bridge embedded firmware logic with a Python-based industrial monitoring GUI. This project emphasizes high-reliability communication protocols, physical-layer diagnostic readiness (CAN Bus & UART), and efficient state-machine telemetry parsing.

---

## 🚀 Key Features

* **Advanced CAN Bus Integration**: Implements Extended Frame (`CAN_ID_EXT`) protocol parsing, handling continuous active reporting (`0xFFFF`) and optimized memory mapping for 32 series cell voltages (`0x11110102 ~ 0x11110109`).
* **Strict Binary Framing & Packing**: Utilizes `#pragma pack(1)` memory alignment in C firmware to ensure zero-padding binary serialization, paired with a robust dual-byte header (`0xAA 0x55`) and checksum validation for reliable serial telemetry transmission.
* **Comprehensive Protection State Machine**: Real-time evaluation of multi-level battery protection triggers (Cell Over/Under-Voltage, Charge/Discharge Overcurrent, and Self-Lock Switch monitoring via 16-bit status words).
* **Multi-Threaded Python PyQt5 GUI**: Decouples serial reading and UI rendering to prevent UI freezing, featuring dynamic status indicators, cell voltage grids, and live logging.

---

## 📄 Protocol Reference
This project implements data parsing and communication logic compliant with standard industrial specifications. You can review the complete technical details in the repository:

* View Complete Manufacturer CAN Protocol Specification (YDE-BTXXSXX锂电池保护板CAN通讯协议)

---

## 🖥️ System Demonstration

**1. Normal Operation State**
* Real-time monitoring of 32 series cell voltages, temperatures, and SOC curve dynamics.
* Stable system telemetry with all status indicators operating in regular green condition.

<img width="1360" height="1111" alt="Image" src="https://github.com/user-attachments/assets/62e2cb60-366d-44ac-bbb0-f22c390a2337" />

**2. Fault Protection State (故障报警状态)**
* Simulated trigger of cell over-voltage, under-voltage, or over-current protection. The state machine captures exceptions instantly via 16-bit status word bitwise operators.
* Immediate protection alert dispatch on GUI

![Fault State](https://github.com/user-attachments/assets/46dfc2fa-8e90-4af5-bd1d-1cb47f22a6c0)

---

## 📂 Project Architecture

```text
/
├── main.c                  # STM32 core firmware (CAN parsing, protection logic, binary packing)
├── bms_protocol.h          # Protocol definitions, data structures, and status word masks
└── bms_industrial_gui.py   # Python PyQt5 multi-threaded monitoring interface

---




