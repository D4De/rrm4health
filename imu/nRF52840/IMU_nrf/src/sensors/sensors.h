#ifndef SENSORS_H
#define SENSORS_H

#include <stdint.h>
#include <stdbool.h>

#include "board_config.h"
#include "global_defs.h"
#include "lsm6dso.h"
#include "nrf_drv_twi.h"
#include "nrf_drv_saadc.h"
#include "nrf_gpio.h"
#include "nrf_log.h"
#include "nrf_power.h"

// ======================================================================
// MACROS AND DEFINES
// ======================================================================

// --------- Sensor Delays & Configuration ------------------------------
#define SENSOR_INIT_DELAY_MS      100
#define SENSOR_RESET_DELAY_MS     50
#define LIS2MDL_DATA_LEN_BYTES    0x06

/**
 * LSM6DSO accelerometer conversion factor when configured at ±4 g.
 * 8192 LSB correspond to 1 g.
 */
#define LSM6DSO_GRAVITY_SCALE_4G      8192.0f

/**
 * LSM6DSO gyroscope sensitivity at ±250 dps.
 * Datasheet sensitivity: 8.75 mdps/LSB.
 */
#define LSM6DSO_GYRO_DPS_PER_LSB_250  0.00875f

// --------- FEATURES Filter Coefficients -------------------------------

/**
 * Second-order IIR coefficients used by the generic preprocessing path.
 *
 * IMPORTANT:
 * These coefficients are applied continuously sample-by-sample in this
 * firmware. This IMU is not used by the SisFall fall-detection model, so
 * the continuous-state implementation is intentional here.
 */
#define FEATURE_FILTER_B0   0.04613188f
#define FEATURE_FILTER_B1   0.09226376f
#define FEATURE_FILTER_B2   0.04613188f
#define FEATURE_FILTER_A1  -1.30728503f
#define FEATURE_FILTER_A2   0.49181255f

#define FEATURE_EPSILON      0.000001f
#define FEATURE_RAD_TO_DEG   57.29577951308232f

// --------- SAADC Constants --------------------------------------------
#define ADC_RESOLUTION_10BIT         1024.0f
#define ADC_REF_VOLTAGE              3.6f
#define BATT_VOLTAGE_DIVIDER_FACTOR  1.5f

// --------- Battery Logic Configuration -------------------------------
#define BATT_ADC_SETTLE_TIME_MS       5
#define BATT_SAMPLES_COUNT            4
#define BATT_FILTER_ALPHA             0.2f
#define BATT_FILTER_COMPLEMENT_BASE   1.0f
#define BATT_FILTER_INIT_VAL         -1.0f
#define BATT_VOLTAGE_MIN              3.0f
#define BATT_VOLTAGE_MAX              4.2f
#define BATT_PERCENTAGE_MIN           0.0f
#define BATT_PERCENTAGE_MAX           100.0f

// --------- Legacy Quaternion Values -----------------------------------
#define QUAT_DUMMY_Q0 0
#define QUAT_DUMMY_Q1 1
#define QUAT_DUMMY_Q2 2
#define QUAT_DUMMY_Q3 3

// ======================================================================
// ENUMS
// ======================================================================

/**
 * @brief Current hardware power source.
 *
 * This only controls periodic battery polling.
 * It does NOT control whether the Battery Service exists in GATT.
 */
typedef enum
{
    POWER_USB,
    POWER_BATTERY,
    POWER_UNKNOWN
} power_source_t;

// ======================================================================
// PUBLIC FUNCTION PROTOTYPES
//
// Keep these comments in sync with the implementation: this file is used as
// the API-level reference for sensor acquisition and preprocessing.
// ======================================================================

/**
 * @brief Initializes the SAADC peripheral.
 *
 * The battery channel itself is configured on demand by sampleBattery().
 */
void saadc_init(void);

/**
 * @brief Initializes LSM6DSO and LIS2MDL.
 *
 * LSM6DSO:
 *   - Accelerometer: 104 Hz, ±4 g
 *   - Gyroscope:     104 Hz, ±250 dps
 *
 * LIS2MDL:
 *   - Used only for RAW mode.
 *
 * @return true if the primary LSM6DSO is initialized successfully.
 */
bool setupSensors(void);

/**
 * @brief Samples and filters the battery percentage.
 *
 * @return Battery charge percentage in range [0, 100].
 */
uint8_t sampleBattery(void);

/**
 * @brief Detects whether the device is currently powered from USB or battery.
 *
 * @return POWER_USB or POWER_BATTERY.
 */
power_source_t detectPowerSource(void);

/**
 * @brief Acquires one RAW sample packet.
 *
 * Includes accelerometer, gyroscope, magnetometer, packet counter and
 * campaign timestamp.
 */
void getSensorData(datapacket_t *p_data,
                   uint16_t current_counter,
                   uint32_t current_timestamp);

/**
 * @brief Fills the legacy quaternion packet.
 *
 * Current implementation still uses placeholder quaternion values because
 * QUAT is not used by the present manager.
 */
void getQuatData(datapacket_quat_t *p_data,
                 uint16_t current_counter,
                 uint32_t current_timestamp);

/**
 * @brief Resets all state used by the FEATURES pipeline.
 *
 * Resets:
 *   - six biquad filter states;
 *   - ring-buffer indexes;
 *   - valid sample count;
 *   - step-size counter;
 *   - first-window state.
 *
 * Call this at the start of every new campaign/configuration.
 */
void resetFeaturePipeline(void);

/**
 * @brief Acquires one ACC+GYRO sample and updates the FEATURES pipeline.
 *
 * The magnetometer is intentionally ignored in FEATURES mode.
 *
 * The function returns false while the first window is still being filled.
 * Once the first window is complete, it returns true and fills p_data.
 * Subsequent feature packets are produced every step_size new samples.
 *
 * @param[out] p_data            Output feature packet.
 * @param[in]  current_counter   Counter of transmitted FEATURES packets.
 * @param[in]  current_timestamp Timestamp associated with this sample.
 * @param[in]  window_size       Number of samples used per feature vector.
 * @param[in]  step_size         Number of new samples between outputs.
 *
 * @return true when a complete feature packet is ready to transmit.
 */
bool getFeatureData(datapacket_features_t *p_data,
                    uint16_t current_counter,
                    uint32_t current_timestamp,
                    uint16_t window_size,
                    uint16_t step_size);

#endif