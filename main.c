#include "bms_protocol.h"
#include <stdio.h>

BMS_Data_t g_bms_data;

/**
 * @brief 发送控制报文让 BMS 开启持续主动上报 (0xFFFF)
 */
void BMS_Start_Reporting(CAN_HandleTypeDef *hcan) {
    CAN_TxHeaderTypeDef tx_header;
    uint32_t mailbox;
    uint8_t tx_data[8] = {0xFF, 0xFF, 0, 0, 0, 0, 0, 0};

    tx_header.ExtId = 0x11010100;     // 控制报文 ID
    tx_header.IDE = CAN_ID_EXT;       // 扩展帧[cite: 17]
    tx_header.RTR = CAN_RTR_DATA;     // 数据帧
    tx_header.DLC = 8;                // 8字节


    if (HAL_CAN_AddTxMessage(hcan, &tx_header, tx_data, &mailbox) != HAL_OK) {
    // 获取 HAL 库的底层错误码，方便定位是哪一个邮箱满了或总线出错
    uint32_t error_code = HAL_CAN_GetError(hcan);
    printf("CAN Tx Failed! Error Code: 0x%lX\r\n", error_code);
}
}

/**
 * @brief 高效简洁的 CAN 接收解析函数
 */
void BMS_Parse_CAN_Message(uint32_t ext_id, uint8_t *data) {
    // 1. 巧妙利用数学区间，把 8 个连续的电压 ID (0x11110102 ~ 0x11110109) 压缩成一个循环处理[cite: 19, 20, 21, 22, 23, 24, 25, 26, 27]
    if (ext_id >= 0x11110102 && ext_id <= 0x11110109) {
        uint8_t base_index = (ext_id - 0x11110102) * 4; // 每帧包含 4 节电压
        for (int i = 0; i < 4; i++) {
            g_bms_data.cell_voltages[base_index + i] = ((uint16_t)data[i * 2] << 8) | data[i * 2 + 1];
        }
        return;
    }

    // 2. 其他独立报文分发
    switch (ext_id) {
        case 0x11110100: // 基础信息、保护/自锁状态字、温度
            g_bms_data.battery_type    = data[0];
            g_bms_data.battery_strings = data[1];
            g_bms_data.status_word     = ((uint16_t)data[2] << 8) | data[3];
            g_bms_data.max_temp        = (int16_t)(((uint16_t)data[4] << 8) | data[5]);
            g_bms_data.min_temp        = (int16_t)(((uint16_t)data[6] << 8) | data[7]);
            break;

        case 0x11110101: // SOC、平均温度、电流、MOS状态
            g_bms_data.soc            = ((uint16_t)data[0] << 8) | data[1];
            g_bms_data.avg_temp       = (int16_t)(((uint16_t)data[2] << 8) | data[3]);
            g_bms_data.current        = (int16_t)(((uint16_t)data[4] << 8) | data[5]);
            g_bms_data.chg_mos_status = data[6];
            g_bms_data.dsg_mos_status = data[7];
            break;

        case 0x11110112: // 容量与循环次数
            g_bms_data.remain_capacity = ((uint16_t)data[0] << 8) | data[1];
            g_bms_data.full_capacity   = ((uint16_t)data[2] << 8) | data[3];
            g_bms_data.cycle_capacity  = ((uint16_t)data[4] << 8) | data[5];
            g_bms_data.cycle_times     = ((uint16_t)data[6] << 8) | data[7];
            break;

        default:
            break;
    }
}

/**
 * @brief 检查是否发生了任意保护 (Bit 0 ~ Bit 14 只要有一个为 1)
 */
bool BMS_Is_Protected(void) {
    return (g_bms_data.status_word & 0x7FFF) != 0; 
}

/**
 * @brief 单体过压保护 (Bit 0)
 */
bool BMS_Is_CellOverVoltage(void) {
    return (g_bms_data.status_word & (1 << 0)) != 0;
}

/**
 * @brief 单体欠压保护 (Bit 1)
 */
bool BMS_Is_CellUnderVoltage(void) {
    return (g_bms_data.status_word & (1 << 1)) != 0;
}

/**
 * @brief 充放电过流保护 (Bit 8 或 Bit 9)
 */
bool BMS_Is_OverCurrent(void) {
    return (g_bms_data.status_word & ((1 << 8) | (1 << 9))) != 0;
}

/**
 * @brief 获取自锁开关状态 (Bit 15)
 * @return true 表示开关断开，false 表示开关闭合
 */
bool BMS_Get_SelfLockSwitch(void) {
    return (g_bms_data.status_word & (1 << 15)) != 0;
}


/**
 * @brief 将完整的 g_bms_data 数据打包为二进制协议帧并通过串口发送给上位机
 * @param huart 串口句柄指针 (例如 &huart1)
 */
void BMS_Send_Binary_Packet(UART_HandleTypeDef *huart) {
    // 1. 定义固定双字节帧头
    uint8_t header[2] = {0xAA, 0x55};
    uint8_t checksum = 0;
    
    // 2. 强制 1 字节对齐，完整映射所有 BMS 核心数据
    #pragma pack(1)
    typedef struct {
        uint8_t  battery_type;
        uint8_t  battery_strings;
        uint16_t status_word;       // 保护状态与自锁开关
        int16_t  max_temp;
        int16_t  min_temp;
        uint16_t soc;
        int16_t  avg_temp;
        int16_t  current;
        uint8_t  chg_mos_status;
        uint8_t  dsg_mos_status;
        uint16_t remain_capacity;
        uint16_t full_capacity;
        uint16_t cycle_capacity;
        uint16_t cycle_times;
        uint16_t cell_voltages[32]; // 完整的 32 串单体电压
    } BMS_Full_Packet_t;
    #pragma pack()

    BMS_Full_Packet_t packet;

    // 3. 将全局 g_bms_data 的数据完整拷贝到发送包中
    packet.battery_type    = g_bms_data.battery_type;
    packet.battery_strings = g_bms_data.battery_strings;
    packet.status_word     = g_bms_data.status_word;
    packet.max_temp        = g_bms_data.max_temp;
    packet.min_temp        = g_bms_data.min_temp;
    packet.soc             = g_bms_data.soc;
    packet.avg_temp        = g_bms_data.avg_temp;
    packet.current         = g_bms_data.current;
    packet.chg_mos_status  = g_bms_data.chg_mos_status;
    packet.dsg_mos_status  = g_bms_data.dsg_mos_status;
    packet.remain_capacity = g_bms_data.remain_capacity;
    packet.full_capacity   = g_bms_data.full_capacity;
    packet.cycle_capacity  = g_bms_data.cycle_capacity;
    packet.cycle_times     = g_bms_data.cycle_times;
    
    for (int i = 0; i < 32; i++) {
        packet.cell_voltages[i] = g_bms_data.cell_voltages[i];
    }

    // 4. 计算校验和（对整个完整数据包做单字节累加求和）
    uint8_t *p_data = (uint8_t*)&packet;
    for (size_t i = 0; i < sizeof(BMS_Full_Packet_t); i++) {
        checksum += p_data[i];
    }

    // 5. 依次通过串口发送：帧头 (2字节) -> 完整数据负载 -> 校验和 (1字节)
    HAL_UART_Transmit(huart, header, 2, HAL_MAX_DELAY);
    HAL_UART_Transmit(huart, (uint8_t*)&packet, sizeof(BMS_Full_Packet_t), HAL_MAX_DELAY);
    HAL_UART_Transmit(huart, &checksum, 1, HAL_MAX_DELAY);
}