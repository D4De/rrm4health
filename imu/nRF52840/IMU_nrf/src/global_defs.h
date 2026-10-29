#ifndef GLOBAL_DEFS_H
#define GLOBAL_DEFS_H

#include <stdint.h>
#include <stdbool.h>

// ======================================================================
// MACROS AND CONSTANTS
//
// This header intentionally documents every public protocol constant because
// the values must stay synchronized with the Python BLE manager.
// ======================================================================

/**
 * @brief Default BLE name template.
 *
 * The last four characters are replaced with the last two bytes of the
 * device address, e.g. IMU7811.
 */
#define IMU_DEFAULT_NAME "IMUXXXX"

// --------- ACK Codes ---------------------------------------------------
#define ACK_OK 0x00
#define ACK_KO 0xFF

// --------- Payload Lengths ---------------------------------------------
#define TIMESTAMP_HEX_LEN      4
#define CONFIGURATION_HEX_LEN  6
#define ACTIVITY_HEX_LEN       1
#define BATTLEVEL_HEX_LEN      1

// --------- Campaign Commands / Modes ----------------------------------
#define START_CAMPAIGN    0x00
#define STOP_CAMPAIGN     0x0F

/**
 * Public campaign mapping shared with the Python BLE manager:
 *
 *   raw=True  -> CAMPAIGN_RAW
 *   raw=False -> CAMPAIGN_FEATURES
 *
 * QUAT is intentionally kept only as a legacy/internal mode and is not
 * selectable from the current manager.
 */
#define CAMPAIGN_RAW       0x00
#define CAMPAIGN_FEATURES  0x01
#define CAMPAIGN_QUAT      0x0F

// --------- Required Setup Messages ------------------------------------
#define MSG_TS    0
#define MSG_CAMP  1
#define MSG_ACK   2
#define REQ_MSG   3

// --------- Defaults ----------------------------------------------------
#define DEFAULT_COUNTER_INIT       0
#define DEFAULT_TIMESTAMP_INIT     0
#define DEFAULT_SAMPLING_FREQUENCY 10

/**
 * @brief Sampling timing configuration.
 *
 * The LSM6DSO accelerometer and gyroscope are configured at 104 Hz.
 * This firmware intentionally accepts campaigns up to 100 Hz.
 *
 * SAMPL_FREQ_ADJ is set to 1.0 so a requested Fs produces a real timer
 * period of approximately 1000/Fs ms. The old 0.5 factor would have caused
 * a 100 Hz campaign to trigger the software timer every 5 ms (~200 Hz),
 * potentially re-reading the same physical sensor sample.
 */
#define SAMPL_FREQ_ADJ                  1.0f
#define MAX_SUPPORTED_SAMPLING_FREQUENCY 100

/**
 * @brief Maximum supported FEATURES window.
 *
 * The feature pipeline uses statically allocated buffers to avoid heap
 * fragmentation and unpredictable allocation failures on the MCU.
 *
 * Increase this value only after checking available RAM.
 */
#define MAX_FEATURE_WINDOW_SIZE 600

/**
 * @brief Number of features transmitted in FEATURES mode.
 *
 * IMPORTANT:
 * This must remain synchronized with:
 *   - extractFeatureVector() in sensors.c
 *   - FEATURE_NAMES in Connect_Bluetooth_Reconnect_features.py
 */
#define FEATURE_COUNT 28

// ======================================================================
// ENUMS AND STRUCTURES
// ======================================================================

/**@brief Possible states of the main IMU state machine. */
typedef enum
{
    STATE_POWER_ON = 0,
    STATE_WAIT_TIMESTAMP = 1,
    STATE_WAIT_CONFIGURATION = 2,
    STATE_SEND_ACK = 3,
    STATE_READY = 4,
    STATE_ACQUISITION = 5,
    STATE_DISCONNECTION = 6,
    STATE_STOP = 7,
    STATE_SLEEP = 8,
    STATE_ZOMBIE = 9
} imu_states_t;

/**
 * @brief Settings for the current acquisition campaign.
 *
 * init_counter has intentionally been removed. Every new campaign starts
 * with counter = 0, matching the current Python manager API.
 */
typedef struct
{
    uint8_t  sampling_frequency; /**< Requested acquisition frequency in Hz. */
    uint16_t interval;           /**< Software sampling interval in ms. */
    bool     raw;                /**< true = RAW, false = FEATURES. */
    uint16_t window_size;        /**< Number of samples in a FEATURES window. */
    uint16_t step_size;          /**< New samples between successive feature vectors. */
} campaign_parameters_t;

/**@brief Generic structure for a 3-axis floating-point sensor value. */
typedef struct
{
    float x, y, z;
} sensor_data_t;

/**
 * @brief RAW transmission packet.
 *
 * Layout is kept compatible with the Python BLE manager:
 * 9 x int16 + uint16 counter + uint32 timestamp = 24 bytes.
 */
typedef struct __attribute__((packed))
{
    int16_t ax, ay, az;
    int16_t gx, gy, gz;
    int16_t mx, my, mz;
    uint16_t counter;
    uint32_t timestamp;
} datapacket_t;

/**
 * @brief Legacy quaternion packet.
 *
 * The current manager does not expose QUAT mode, but the type and
 * characteristic are retained for backward/internal compatibility.
 */
typedef struct __attribute__((packed))
{
    uint32_t q0, q1, q2, q3;
    uint16_t counter;
    uint32_t timestamp;
} datapacket_quat_t;

/**
 * @brief FEATURES transmission packet.
 *
 * Layout expected by the Python manager:
 *
 *   28 x float32  = 112 bytes
 *   uint16 counter =  2 bytes
 *   uint32 timestamp = 4 bytes
 *   --------------------------------
 *   total = 118 bytes
 */
typedef struct __attribute__((packed))
{
    float features[FEATURE_COUNT];
    uint16_t counter;
    uint32_t timestamp;
} datapacket_features_t;

/**@brief Human-readable local date/time representation. */
typedef struct
{
    uint8_t yy, mm, dd, HH, MM, SS;
    uint16_t cents;
} timestamp_data_t;

#endif // GLOBAL_DEFS_H