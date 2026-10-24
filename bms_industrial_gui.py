import sys
import math
import random
import struct
import serial
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QProgressBar, QGroupBox, QComboBox,
    QPushButton, QFrame, QTextEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QSplitter
)
import pyqtgraph as pg

# ==================== 1. 协议与状态字位定义 ====================
PACKET_FORMAT = "<BBHhhHhhBBHHHH32H"
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)  # 88 字节

# BMS 保护状态字位映射表 (Bit0 - Bit15)
PROTECTION_BIT_MAP = {
    0:  "单体过压保护 (Cell Over Voltage)",
    1:  "单体欠压保护 (Cell Under Voltage)",
    2:  "整组过压保护 (Pack Over Voltage)",
    3:  "整组欠压保护 (Pack Under Voltage)",
    4:  "充电过温保护 (Chg Over Temp)",
    5:  "充电低温保护 (Chg Under Temp)",
    6:  "放电过温保护 (Dsg Over Temp)",
    7:  "放电低温保护 (Dsg Under Temp)",
    8:  "充电过流保护 (Chg Over Current)",
    9:  "放电过流保护 (Dsg Over Current)",
    10: "短路保护 (Short Circuit)",
    11: "前端 AFE 芯片异常 (AFE Fault)",
    12: "软件锁定 MOS (MOS Locked)"
}


# ==================== 2. 后台异步通信线程 ====================
class BMSWorkerThread(QThread):
    """
    后台数据接收与解包线程，实现 UI 主线程与串口/协议解析解耦，确保界面高帧率不卡顿
    """
    data_received = pyqtSignal(dict)
    log_signal = pyqtSignal(str, str) # (message, level: "INFO"/"WARN"/"ERROR")

    def __init__(self, port="COM3", baudrate=115200, use_mock=False):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.use_mock = use_mock
        self.running = True

    def run(self):
        if self.use_mock:
            self.log_signal.emit(">>> 已启动 Mock 虚拟数据源 (Demo Mode)...", "WARN")
            self.run_mock()
        else:
            self.log_signal.emit(f"正在尝试打开物理串口 {self.port} (波特率: {self.baudrate})...", "INFO")
            self.run_serial()

    def run_serial(self):
        try:
            ser = serial.Serial(self.port, self.baudrate, timeout=1)
            self.log_signal.emit(f"串口 {self.port} 打开成功，开始监听 BMS 网关数据流...", "INFO")
        except Exception as e:
            self.log_signal.emit(f"串口打开失败: {e}", "ERROR")
            return

        while self.running:
            try:
                # 帧头同步 (0xAA 0x55)
                header = ser.read(2)
                if header != b"\xaa\x55":
                    continue

                # 读取固定长度 Payload[cite: 18]
                payload = ser.read(PACKET_SIZE)
                if len(payload) != PACKET_SIZE:
                    continue

                # 校验和判定[cite: 18]
                recv_checksum = ser.read(1)
                if not recv_checksum:
                    continue

                calc_checksum = sum(payload) & 0xFF
                if calc_checksum != recv_checksum[0]:
                    self.log_signal.emit(f"帧校验和错误 (计算值: 0x{calc_checksum:02X}, 接收值: 0x{recv_checksum[0]:02X})", "WARN")
                    continue

                # 二进制解包[cite: 18]
                unpacked = struct.unpack(PACKET_FORMAT, payload)
                bms_data = self.parse_payload(unpacked)
                self.data_received.emit(bms_data)

            except Exception as e:
                if self.running:
                    self.log_signal.emit(f"数据接收异常: {e}", "ERROR")

        if 'ser' in locals() and ser.is_open:
            ser.close()
            self.log_signal.emit("物理串口已安全关闭。", "INFO")

    def run_mock(self):
        """生成逼真的工业模拟信号数据"""
        t = 0
        while self.running:
            soc = 82.5 - (t * 0.05) % 100
            current = 12.8 * math.sin(t / 5.0)
            avg_temp = 27.5 + 1.5 * math.cos(t / 10.0)

            # 模拟 16 串电池电压（带轻微噪声与压差）
            voltages = []
            for i in range(32):
                if i < 16:
                    base_v = 3300 if i != 3 else 3240  # 故意让第 4 串电压偏低，展示压差与最值高亮
                    v = int(base_v + 15 * math.sin(t / 3.0 + i) + random.randint(-3, 3))
                else:
                    v = 0 # 未使用的串数
                voltages.append(v)

            # 模拟偶尔触发告警状态字（如单体欠压）
            status_word = 0x0000
            if math.sin(t / 12.0) > 0.8:
                status_word |= (1 << 1) # 触发单体欠压保护[cite: 18]

            mock_data = {
                "battery_type": 0,          # 0: 磷酸铁锂[cite: 17]
                "battery_strings": 16,      # 16 串[cite: 17]
                "status_word": status_word,
                "max_temp": avg_temp + 1.8,
                "min_temp": avg_temp - 1.2,
                "soc": max(0.0, min(100.0, soc)),
                "avg_temp": avg_temp,
                "current": current,
                "chg_mos": 1,
                "dsg_mos": 1,
                "remain_cap": 82.5,
                "full_cap": 100.0,
                "cycle_cap": 25.0,
                "cycle_times": 142,
                "voltages": voltages
            }
            self.data_received.emit(mock_data)
            self.msleep(400) # 对应 BMS 400ms 上报周期
            t += 0.4

    def parse_payload(self, unpacked):
        return {
            "battery_type": unpacked[0],
            "battery_strings": unpacked[1],
            "status_word": unpacked[2],
            "max_temp": unpacked[3] / 10.0,
            "min_temp": unpacked[4] / 10.0,
            "soc": unpacked[5] / 100.0,
            "avg_temp": unpacked[6] / 10.0,
            "current": unpacked[7] / 100.0,
            "chg_mos": unpacked[8],
            "dsg_mos": unpacked[9],
            "remain_cap": unpacked[10] / 10.0,
            "full_cap": unpacked[11] / 10.0,
            "cycle_cap": unpacked[12] / 10.0,
            "cycle_times": unpacked[13],
            "voltages": unpacked[14:46],
        }

    def stop(self):
        self.running = False
        self.wait()


# ==================== 3. 主界面 Dashboard (PyQt5) ====================
class BMSIndustrialDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("STM32-BMS 储能电池网关实时监控平台 v1.0")
        self.resize(1360, 850)
        self.worker = None

        pg.setConfigOption('background', '#121316')
        pg.setConfigOption('foreground', '#B0B4C0')

        self.init_ui()
        self.apply_industrial_qss()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # ------------------ 1. 顶部状态与通信控制栏 ------------------
        top_bar = QHBoxLayout()
        
        logo_label = QLabel("⚡ STM32-BMS GATEWAY TELEMETRY")
        logo_label.setFont(QFont("Consolas", 24, QFont.Bold))
        logo_label.setStyleSheet("color: #409EFF; letter-spacing: 1px;")
        top_bar.addWidget(logo_label)

        top_bar.addStretch()

        top_bar.addWidget(QLabel("端口:"))
        self.port_combo = QComboBox()
        self.port_combo.addItems(["COM1", "COM2", "COM3", "COM4", "/dev/ttyUSB0"])
        self.port_combo.setCurrentText("COM3")
        top_bar.addWidget(self.port_combo)

        self.btn_serial = QPushButton("开启物理串口监听")
        self.btn_serial.clicked.connect(self.toggle_serial)
        top_bar.addWidget(self.btn_serial)

        self.btn_mock = QPushButton("启动 Demo 模拟数据源")
        self.btn_mock.setStyleSheet("background-color: #67C23A; color: white;")
        self.btn_mock.clicked.connect(self.toggle_mock)
        top_bar.addWidget(self.btn_mock)

        main_layout.addLayout(top_bar)

        # ------------------ 2. 告警通知高亮横幅 ------------------
        self.banner_alert = QLabel("SYSTEM READY: 告警系统就绪，等待下位机遥测数据输入...")
        self.banner_alert.setFixedHeight(32)
        self.banner_alert.setAlignment(Qt.AlignCenter)
        self.banner_alert.setStyleSheet("background-color: #1E222D; color: #67C23A; font-weight: bold; border-radius: 4px;")
        main_layout.addWidget(self.banner_alert)

        # ------------------ 3. 核心分屏区域 ------------------
        splitter = QSplitter(Qt.Horizontal)

        # --- 左侧卡片面板 ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # SOC 核心卡片
        soc_group = QGroupBox("电池剩余电量 (SOC)")
        soc_lay = QVBoxLayout()
        self.soc_bar = QProgressBar()
        self.soc_bar.setFixedHeight(28)
        self.soc_bar.setRange(0, 100)
        self.soc_bar.setValue(0)
        soc_lay.addWidget(self.soc_bar)
        soc_group.setLayout(soc_lay)
        left_layout.addWidget(soc_group)

        # 核心指标网格 (2x3)
        metrics_group = QGroupBox("遥测核心参数")
        grid = QGridLayout()
        self.lbl_current   = self.add_metric_card(grid, "总电流", "0.00 A", 0, 0)
        self.lbl_pack_v    = self.add_metric_card(grid, "总电压(估算)", "0.00 V", 0, 1)
        self.lbl_v_diff    = self.add_metric_card(grid, "最大压差", "0 mV", 1, 0)
        self.lbl_avg_temp  = self.add_metric_card(grid, "平均温度", "0.0 ℃", 1, 1)
        self.lbl_max_temp  = self.add_metric_card(grid, "最高/最低温", "0 / 0 ℃", 2, 0)
        self.lbl_cycles    = self.add_metric_card(grid, "循环次数", "0 次", 2, 1)
        metrics_group.setLayout(grid)
        left_layout.addWidget(metrics_group)

        # 保护位状态网格（模拟状态灯）
        status_group = QGroupBox("拓扑与 MOS 状态")
        status_lay = QGridLayout()
        self.lbl_chg_mos = QLabel("充电 MOS: -")
        self.lbl_dsg_mos = QLabel("放电 MOS: -")
        self.lbl_type    = QLabel("类型: 磷酸铁锂")
        self.lbl_strings = QLabel("串数: 16 串")
        self.lbl_lock    = QLabel("自锁开关: 闭合")

        status_lay.addWidget(self.lbl_chg_mos, 0, 0)
        status_lay.addWidget(self.lbl_dsg_mos, 0, 1)
        status_lay.addWidget(self.lbl_type, 1, 0)
        status_lay.addWidget(self.lbl_strings, 1, 1)
        status_lay.addWidget(self.lbl_lock, 2, 0)
        status_group.setLayout(status_lay)
        left_layout.addWidget(status_group)

        # 日志输出终端
        log_group = QGroupBox("日志诊断终端")
        log_lay = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background-color: #0B0C0E; color: #8F939D; font-family: Consolas; font-size: 16px;")
        log_lay.addWidget(self.log_text)
        log_group.setLayout(log_lay)
        left_layout.addWidget(log_group)

        splitter.addWidget(left_widget)

        # --- 右侧柱状图与实时图表区 ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        chart_group = QGroupBox("32 串单体电压分布柱状图 (实时 mV 标注)")
        chart_lay = QVBoxLayout()

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel('bottom', '单体编号 (Cell Index)')
        self.plot_widget.setLabel('left', '电压 (mV)')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget.setYRange(2500, 4200)

        # 32 串柱状图
        self.x_bars = list(range(1, 17))
        self.bar_item = pg.BarGraphItem(x=self.x_bars, height=[0]*16, width=0.6, brush='#409EFF')
        self.plot_widget.addItem(self.bar_item)

        chart_lay.addWidget(self.plot_widget)
        chart_group.setLayout(chart_lay)
        right_layout.addWidget(chart_group)

        splitter.addWidget(right_widget)

        # 设置左右比例 35% : 65%
        splitter.setSizes([450, 910])
        main_layout.addWidget(splitter)

    def add_metric_card(self, layout, title, default_val, row, col):
        frame = QFrame()
        frame.setStyleSheet("background-color: #1A1D24; border-radius: 6px; padding: 6px;")
        vbox = QVBoxLayout(frame)
        vbox.setSpacing(2)
        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("color: #8F939D; font-size: 11px;")
        lbl_v = QLabel(default_val)
        lbl_v.setFont(QFont("Segoe UI", 17, QFont.Bold))
        lbl_v.setStyleSheet("color: #E6A23C;")
        vbox.addWidget(lbl_t)
        vbox.addWidget(lbl_v)
        layout.addWidget(frame, row, col)
        return lbl_v

    # ------------------ 4. 核心逻辑处理与界面渲染 ------------------
    def update_dashboard(self, d):
        """处理遥测数据，驱动 UI 渲染"""
        # 1. 动态更新 SOC 进度条
        soc = int(d["soc"])
        self.soc_bar.setValue(soc)
        if soc < 20:
            self.soc_bar.setStyleSheet("QProgressBar::chunk { background-color: #F56C6C; }")
        elif soc < 50:
            self.soc_bar.setStyleSheet("QProgressBar::chunk { background-color: #E6A23C; }")
        else:
            self.soc_bar.setStyleSheet("QProgressBar::chunk { background-color: #67C23A; }")

        # 2. 刷新核心物理指标
        self.lbl_current.setText(f"{d['current']:.2f} A")
        self.lbl_avg_temp.setText(f"{d['avg_temp']:.1f} ℃")
        self.lbl_max_temp.setText(f"{d['max_temp']:.1f} / {d['min_temp']:.1f} ℃")
        self.lbl_cycles.setText(f"{d['cycle_times']} 次")

        # 针对有效串数的电压分析[cite: 17]
        valid_strings = d["battery_strings"] if d["battery_strings"] > 0 else 16
        voltages = d["voltages"][:valid_strings]
        if voltages:
            v_max = max(voltages)
            v_min = min(voltages)
            v_sum = sum(voltages) / 1000.0
            self.lbl_pack_v.setText(f"{v_sum:.2f} V")
            self.lbl_v_diff.setText(f"{v_max - v_min} mV")

            x_bars = list(range(1, valid_strings + 1))
            self.bar_item.setOpts(x=x_bars, height=list(voltages))
            self.plot_widget.setYRange(max(0, v_min - 150), v_max + 150)
        # 3. MOS 状态与硬件开关
        self.lbl_chg_mos.setText(f"充电 MOS: {'开启 🟢' if d['chg_mos'] else '关闭 🔴'}")
        self.lbl_dsg_mos.setText(f"放电 MOS: {'开启 🟢' if d['dsg_mos'] else '关闭 🔴'}")
        self.lbl_type.setText(f"类型: {'磷酸铁锂' if d['battery_type'] == 0 else '三元锂'}")
        self.lbl_strings.setText(f"配置串数: {valid_strings} 串")

        # 自锁开关位解析 (Bit 15)[cite: 18]
        status_word = d["status_word"]
        self.lbl_lock.setText(f"自锁开关: {'断开 🔴' if (status_word & 0x8000) else '闭合 🟢'}")



        # 5. 状态字 Bit 译码与告警高亮处理[cite: 18]
        active_faults = []
        for bit_idx, desc in PROTECTION_BIT_MAP.items():
            if status_word & (1 << bit_idx):
                active_faults.append(desc)

        if active_faults:
            fault_msg = " | ".join(active_faults)
            self.banner_alert.setText(f"⚠️ 系统告警触发: {fault_msg}")
            self.banner_alert.setStyleSheet("background-color: #7C1818; color: #FFFFFF; font-weight: bold; border-radius: 4px;")
            self.append_log(f"[ALERT] 状态字触发告警 0x{status_word:04X}: {fault_msg}", "ERROR")
        else:
            self.banner_alert.setText("SYSTEM HEALTHY: 下位机连接正常，未触发任何硬件保护项")
            self.banner_alert.setStyleSheet("background-color: #1B382B; color: #67C23A; font-weight: bold; border-radius: 4px;")

    def append_log(self, msg, level="INFO"):
        color = "#8F939D"
        if level == "WARN":
            color = "#E6A23C"
        elif level == "ERROR":
            color = "#EB3E3E"
        self.log_text.append(f"<span style='color:{color};'>[{level}] {msg}</span>")

    # ------------------ 5. 线程通信控制 ------------------
    def toggle_serial(self):
        if self.worker and self.worker.isRunning():
            self.stop_worker()
            self.btn_serial.setText("开启物理串口监听")
        else:
            port = self.port_combo.currentText()
            self.start_worker(port=port, use_mock=False)
            self.btn_serial.setText("断开串口")

    def toggle_mock(self):
        if self.worker and self.worker.isRunning():
            self.stop_worker()
            self.btn_mock.setText("启动 Demo 模拟数据源")
        else:
            self.start_worker(use_mock=True)
            self.btn_mock.setText("停止 Demo 模式")

    def start_worker(self, port="COM3", use_mock=False):
        self.worker = BMSWorkerThread(port=port, baudrate=115200, use_mock=use_mock)
        self.worker.data_received.connect(self.update_dashboard)
        self.worker.log_signal.connect(self.append_log)
        self.worker.start()

    def stop_worker(self):
        if self.worker:
            self.worker.stop()
            self.worker = None

    def apply_industrial_qss(self):
        dark_qss = """
        QMainWindow { background-color: #121316; }
        QGroupBox {
            color: #409EFF;
            font-weight: bold;
            border: 1px solid #232731;
            border-radius: 6px;
            margin-top: 10px;
            padding-top: 8px;
        }
        QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
        QLabel { color: #DCDFE6; font-size: 25px; }
        QPushButton {
            background-color: #409EFF;
            color: white;
            border-radius: 4px;
            padding: 5px 10px;
            font-weight: bold;
        }
        QPushButton:hover { background-color: #66B1FF; }
        QComboBox {
            background-color: #1D212A;
            color: #DCDFE6;
            border: 1px solid #363B46;
            border-radius: 4px;
            padding: 3px;
        }
        QProgressBar {
            border: 1px solid #363B46;
            border-radius: 4px;
            text-align: center;
            color: white;
            font-weight: bold;
            background-color: #1D212A;
        }
        """
        self.setStyleSheet(dark_qss)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BMSIndustrialDashboard()
    window.show()
    sys.exit(app.exec_())