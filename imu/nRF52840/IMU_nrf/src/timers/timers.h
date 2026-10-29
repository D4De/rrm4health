/**
 * @file timers.h
 * @brief Public API for application timers and timer flags.
 */

#ifndef TIMERS_H
#define TIMERS_H

#include <stdint.h>
#include <stdbool.h>
#include "board_config.h"
#include "app_timer.h"
#include "nrf_gpio.h"

/** Period between battery measurements while running on battery power. */
#define BATTERY_SAMPLING_INTERVAL_MS 10000
/** Maximum time allowed for a temporary BLE disconnection. */
#define RECONNECT_TIMEOUT_MS         30000

/** Initialize all firmware timers. */
void timers_init(void);
/** Return/clear pending IMU sample request. */
bool check_and_clear_imu_flag(void);
/** Return/clear pending battery sample request. */
bool check_and_clear_battery_flag(void);
/** Return/clear expired reconnect timeout. */
bool check_and_clear_disconnect_flag(void);
/** Start repeated IMU sampling timer. */
void imu_sampling_timer_start(uint16_t interval_ms);
/** Stop IMU sampling timer. */
void imu_sampling_timer_stop(void);
/** Start repeated battery timer. */
void battery_timer_start(void);
/** Stop repeated battery timer. */
void battery_timer_stop(void);
/** Start single-shot disconnect timer. */
void disconnect_timeout_timer_start(void);
/** Stop single-shot disconnect timer. */
void disconnect_timeout_timer_stop(void);

#endif