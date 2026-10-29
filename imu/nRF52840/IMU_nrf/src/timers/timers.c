/**
 * @file timers.c
 * @brief Application timers used for IMU sampling, battery polling and
 *        reconnection timeout management.
 *
 * Timer callbacks only raise volatile flags. Actual sensor/BLE work is kept
 * in the main loop, avoiding heavy processing inside timer interrupt context.
 */

#include "timers.h"

/** Repeated timer driving IMU sampling cadence. */
APP_TIMER_DEF(m_imu_timer_id);
/** Repeated timer driving periodic battery refresh. */
APP_TIMER_DEF(m_battery_timer_id);
/** Single-shot timer limiting the BLE reconnection window. */
APP_TIMER_DEF(m_disconnect_timer_id);

static volatile bool g_sample_imu_flag = false;
static volatile bool g_sample_battery_flag = false;
static volatile bool g_disconnect_timeout_flag = false;

/** @brief Timer callback: request one IMU sample in the main loop. */
static void imu_timer_handler(void *p_context)
{
    (void)p_context;
    g_sample_imu_flag = true;
}

/** @brief Timer callback: request one battery sample in the main loop. */
static void battery_timer_handler(void *p_context)
{
    (void)p_context;
    g_sample_battery_flag = true;
}

/** @brief Timer callback: signal expiration of reconnection timeout. */
static void disconnect_timer_handler(void *p_context)
{
    (void)p_context;
    g_disconnect_timeout_flag = true;
}

/** @brief Initializes app_timer and creates all three firmware timers. */
void timers_init(void)
{
    app_timer_init();
    app_timer_create(&m_imu_timer_id, APP_TIMER_MODE_REPEATED, imu_timer_handler);
    app_timer_create(&m_battery_timer_id, APP_TIMER_MODE_REPEATED, battery_timer_handler);
    app_timer_create(&m_disconnect_timer_id, APP_TIMER_MODE_SINGLE_SHOT, disconnect_timer_handler);
}

/** @brief Atomically consumes the pending IMU-sample flag. */
bool check_and_clear_imu_flag(void)
{
    if (!g_sample_imu_flag) return false;
    g_sample_imu_flag = false;
    return true;
}

/** @brief Atomically consumes the pending battery-sample flag. */
bool check_and_clear_battery_flag(void)
{
    if (!g_sample_battery_flag) return false;
    g_sample_battery_flag = false;
    return true;
}

/** @brief Atomically consumes the disconnect-timeout flag. */
bool check_and_clear_disconnect_flag(void)
{
    if (!g_disconnect_timeout_flag) return false;
    g_disconnect_timeout_flag = false;
    return true;
}

/** @brief Starts/restarts repeated IMU sampling with the given period. */
void imu_sampling_timer_start(uint16_t interval_ms)
{
    if (interval_ms == 0) return;
    app_timer_stop(m_imu_timer_id);
    app_timer_start(m_imu_timer_id, APP_TIMER_TICKS(interval_ms), NULL);
}

/** @brief Stops the repeated IMU sampling timer. */
void imu_sampling_timer_stop(void) { app_timer_stop(m_imu_timer_id); }

/** @brief Starts/restarts periodic battery sampling at 10 s. */
void battery_timer_start(void)
{
    app_timer_stop(m_battery_timer_id);
    app_timer_start(m_battery_timer_id, APP_TIMER_TICKS(BATTERY_SAMPLING_INTERVAL_MS), NULL);
}

/** @brief Stops periodic battery sampling. */
void battery_timer_stop(void) { app_timer_stop(m_battery_timer_id); }

/** @brief Starts/restarts the single-shot reconnection timeout. */
void disconnect_timeout_timer_start(void)
{
    app_timer_stop(m_disconnect_timer_id);
    app_timer_start(m_disconnect_timer_id, APP_TIMER_TICKS(RECONNECT_TIMEOUT_MS), NULL);
}

/** @brief Stops the reconnection timeout timer. */
void disconnect_timeout_timer_stop(void) { app_timer_stop(m_disconnect_timer_id); }