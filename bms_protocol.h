#ifndef __BMS_PROTOCOL_H
#define __BMS_PROTOCOL_H

#include <stdint.h>
#include <stdbool.h>
#include "stm32f1xx_hal.h"

// 定义精简核心的 BMS 数据结构体
typedef struct {
    uint8_t battery_type;       // 电池类型：0-磷酸铁锂，1-三元锂[cite: 17]
    uint8_t battery_strings;    // 电池串数：0-自动识别[cite: 17]
    uint16_t status_word;       // 16位状态字 (Bit0-14: 保护状态, Bit15: 自锁开关)[cite: 18]
    int16_t max_temp;           // 最高温度 (单位: 0.1℃)[cite: 18]
    int16_t min_temp;           // 最低温度 (单位: 0.1℃)[cite: 18]
    
    uint16_t soc;               // 剩余容量百分比 (单位: 0.01%)[cite: 18, 19]
    int16_t avg_temp;           // 平均温度 (单位: 0.1℃)[cite: 19]
    int16_t current;            // 总电流 (单位: 0.01A，正充负放)[cite: 19]
    uint8_t chg_mos_status;     // 充电 MOS 状态：0-关闭，1-开启[cite: 19]
    uint8_t dsg_mos_status;     // 放电 MOS 状态：0-关闭，1-开启[cite: 19]

    uint16_t remain_capacity;   // 剩余容量 (单位: 0.1AH)[cite: 26]
    uint16_t full_capacity;     // 满充容量 (单位: 0.1AH)[cite: 26]
    uint16_t cycle_capacity;    // 循环容量 (单位: 0.1AH)[cite: 26, 27]
    uint16_t cycle_times;       // 循环次数[cite: 27]

    uint16_t cell_voltages[32]; // 32串单体电压数组 (单位: mV)[cite: 19, 20, 21, 22, 23, 24, 25, 26, 27]
} BMS_Data_t;

extern BMS_Data_t g_bms_data;

// 核心函数声明
void BMS_Start_Reporting(CAN_HandleTypeDef *hcan);
void BMS_Parse_CAN_Message(uint32_t ext_id, uint8_t *data);

// 核心保护状态判断（简洁、不冗余）
bool BMS_Is_Protected(void);            // 是否触发了任意保护
bool BMS_Is_CellOverVoltage(void);      // 单体过压 (Bit 0)[cite: 18]
bool BMS_Is_CellUnderVoltage(void);     // 单体欠压 (Bit 1)[cite: 18]
bool BMS_Is_OverCurrent(void);          // 过流保护 (Bit 8 或 Bit 9)[cite: 18]
bool BMS_Get_SelfLockSwitch(void);      // 自锁开关状态 (Bit 15，0:闭合, 1:断开)[cite: 18]

#endif