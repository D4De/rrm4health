/**
 * @file sensors.c
 * @brief Sensor acquisition, battery management and FEATURES preprocessing.
 *
 * FEATURES mode uses:
 *   - LSM6DSO accelerometer and gyroscope only;
 *   - a persistent second-order IIR filter per axis;
 *   - a circular window buffer;
 *   - 28 derived features in the exact order expected by the Python manager.
 *
 * IMPORTANT WHEN ADDING/REMOVING FEATURES:
 *   1. Update FEATURE_COUNT in global_defs.h.
 *   2. Update extractFeatureVector() below.
 *   3. Keep outFeatures[] ordering synchronized with FEATURE_NAMES in
 *      Connect_Bluetooth_Reconnect_features.py.
 *   4. The Python packet length/format are derived automatically from
 *      FEATURE_NAMES, so no manual packet-size change is required there.
 *
 * Magnetometer samples remain available in RAW mode but are deliberately
 * excluded from FEATURES mode.
 */

#include "sensors.h"

#include <float.h>
#include <math.h>
#include <string.h>

/** Configured accelerometer full scale: ±4 g. */
static uint8_t        acc_fs_sel = G_4;
static accel_values_t accel_data;
static gyro_values_t  gyro_data;
static magn_values_t  magn_data;
static int16_t        gravity_scale = 8192;

// ======================================================================
// FEATURES PIPELINE
// ======================================================================

/** State variables of one direct-form second-order IIR filter. */
typedef struct
{
    float x1, x2, y1, y2;
} biquad_state_t;

static biquad_state_t feature_filters[6];

static float feature_ax[MAX_FEATURE_WINDOW_SIZE];
static float feature_ay[MAX_FEATURE_WINDOW_SIZE];
static float feature_az[MAX_FEATURE_WINDOW_SIZE];
static float feature_gx[MAX_FEATURE_WINDOW_SIZE];
static float feature_gy[MAX_FEATURE_WINDOW_SIZE];
static float feature_gz[MAX_FEATURE_WINDOW_SIZE];

static uint16_t feature_write_index = 0;
static uint16_t feature_valid_samples = 0;
static uint16_t feature_samples_since_output = 0;
static bool feature_first_output_done = false;

/** @brief Clears one filter state to zero. */
static void reset_biquad(biquad_state_t *state)
{
    memset(state, 0, sizeof(*state));
}

/** @brief Filters one sample and updates the persistent biquad state. */
static float process_biquad(biquad_state_t *state, float x)
{
    float y =
        FEATURE_FILTER_B0 * x +
        FEATURE_FILTER_B1 * state->x1 +
        FEATURE_FILTER_B2 * state->x2 -
        FEATURE_FILTER_A1 * state->y1 -
        FEATURE_FILTER_A2 * state->y2;

    state->x2 = state->x1;
    state->x1 = x;
    state->y2 = state->y1;
    state->y1 = y;

    return y;
}

/**
 * @brief Resets all FEATURES buffers, indexes, counters and IIR states.
 */
void resetFeaturePipeline(void)
{
    for (uint8_t i = 0; i < 6; i++)
        reset_biquad(&feature_filters[i]);

    feature_write_index = 0;
    feature_valid_samples = 0;
    feature_samples_since_output = 0;
    feature_first_output_done = false;
}

/**
 * @brief Maps chronological window position to the circular-buffer index.
 */
static uint16_t ring_index(uint16_t i, uint16_t window_size)
{
    if (feature_valid_samples < window_size)
        return i;

    return (uint16_t)((feature_write_index + i) % window_size);
}

/**
 * @brief Computes the 28-feature vector from the current filtered window.
 *
 * Feature order MUST remain identical to Python FEATURE_NAMES.
 */
static void extractFeatureVector(float outFeatures[FEATURE_COUNT],
                                 uint16_t window_size)
{
    float sum_ax = 0.0f, sum_ay = 0.0f, sum_az = 0.0f;
    float sum_gx = 0.0f, sum_gy = 0.0f, sum_gz = 0.0f;
    float sum_acc_mag = 0.0f, sum_gyro_mag = 0.0f;

    float max_ax = -FLT_MAX, max_ay = -FLT_MAX, max_az = -FLT_MAX;
    float max_gx = -FLT_MAX, max_gy = -FLT_MAX, max_gz = -FLT_MAX;
    float max_acc_mag = -FLT_MAX, max_gyro_mag = -FLT_MAX;

    for (uint16_t i = 0; i < window_size; i++)
    {
        uint16_t idx = ring_index(i, window_size);

        float ax = feature_ax[idx];
        float ay = feature_ay[idx];
        float az = feature_az[idx];
        float gx = feature_gx[idx];
        float gy = feature_gy[idx];
        float gz = feature_gz[idx];

        float acc_mag = sqrtf(ax * ax + ay * ay + az * az);
        float gyro_mag = sqrtf(gx * gx + gy * gy + gz * gz);

        sum_ax += ax; sum_ay += ay; sum_az += az;
        sum_gx += gx; sum_gy += gy; sum_gz += gz;
        sum_acc_mag += acc_mag;
        sum_gyro_mag += gyro_mag;

        if (ax > max_ax) max_ax = ax;
        if (ay > max_ay) max_ay = ay;
        if (az > max_az) max_az = az;
        if (gx > max_gx) max_gx = gx;
        if (gy > max_gy) max_gy = gy;
        if (gz > max_gz) max_gz = gz;
        if (acc_mag > max_acc_mag) max_acc_mag = acc_mag;
        if (gyro_mag > max_gyro_mag) max_gyro_mag = gyro_mag;
    }

    float inv_n = 1.0f / (float)window_size;

    float mean_ax = sum_ax * inv_n;
    float mean_ay = sum_ay * inv_n;
    float mean_az = sum_az * inv_n;
    float mean_gx = sum_gx * inv_n;
    float mean_gy = sum_gy * inv_n;
    float mean_gz = sum_gz * inv_n;
    float mean_acc_mag = sum_acc_mag * inv_n;
    float mean_gyro_mag = sum_gyro_mag * inv_n;

    float var_ax = 0.0f, var_ay = 0.0f, var_az = 0.0f;
    float var_gx = 0.0f, var_gy = 0.0f, var_gz = 0.0f;
    float var_acc_mag = 0.0f, var_gyro_mag = 0.0f;
    float dynamic_sma_sum = 0.0f;
    float jerk_sum = 0.0f;
    float jerk_max = 0.0f;
    float previous_acc_mag = 0.0f;
    bool have_previous = false;

    for (uint16_t i = 0; i < window_size; i++)
    {
        uint16_t idx = ring_index(i, window_size);

        float ax = feature_ax[idx];
        float ay = feature_ay[idx];
        float az = feature_az[idx];
        float gx = feature_gx[idx];
        float gy = feature_gy[idx];
        float gz = feature_gz[idx];

        float acc_mag = sqrtf(ax * ax + ay * ay + az * az);
        float gyro_mag = sqrtf(gx * gx + gy * gy + gz * gz);

        float dax = ax - mean_ax;
        float day = ay - mean_ay;
        float daz = az - mean_az;
        float dgx = gx - mean_gx;
        float dgy = gy - mean_gy;
        float dgz = gz - mean_gz;
        float dam = acc_mag - mean_acc_mag;
        float dgm = gyro_mag - mean_gyro_mag;

        var_ax += dax * dax;
        var_ay += day * day;
        var_az += daz * daz;
        var_gx += dgx * dgx;
        var_gy += dgy * dgy;
        var_gz += dgz * dgz;
        var_acc_mag += dam * dam;
        var_gyro_mag += dgm * dgm;

        dynamic_sma_sum += fabsf(dax) + fabsf(day) + fabsf(daz);

        if (have_previous)
        {
            float jerk = fabsf(acc_mag - previous_acc_mag);
            jerk_sum += jerk;
            if (jerk > jerk_max) jerk_max = jerk;
        }

        previous_acc_mag = acc_mag;
        have_previous = true;
    }

    float std_ax = sqrtf(var_ax * inv_n);
    float std_ay = sqrtf(var_ay * inv_n);
    float std_az = sqrtf(var_az * inv_n);
    float std_gx = sqrtf(var_gx * inv_n);
    float std_gy = sqrtf(var_gy * inv_n);
    float std_gz = sqrtf(var_gz * inv_n);
    float std_acc_mag = sqrtf(var_acc_mag * inv_n);
    float std_gyro_mag = sqrtf(var_gyro_mag * inv_n);

    float tilt_ratio = mean_ax / (mean_acc_mag + FEATURE_EPSILON);
    if (tilt_ratio > 1.0f) tilt_ratio = 1.0f;
    if (tilt_ratio < -1.0f) tilt_ratio = -1.0f;

    float tilt = acosf(tilt_ratio) * FEATURE_RAD_TO_DEG;
    float dynamic_sma = dynamic_sma_sum * inv_n;
    float jerk_mean = (window_size > 1) ? jerk_sum / (float)(window_size - 1) : 0.0f;

    /*
     * IMPORTANT: this order MUST match FEATURE_NAMES in the Python manager.
     * When adding/removing features, update both sides together.
     */
    outFeatures[0]  = max_acc_mag;
    outFeatures[1]  = mean_acc_mag;
    outFeatures[2]  = std_acc_mag;
    outFeatures[3]  = max_gyro_mag;
    outFeatures[4]  = mean_gyro_mag;
    outFeatures[5]  = std_gyro_mag;
    outFeatures[6]  = mean_ax;
    outFeatures[7]  = max_ax;
    outFeatures[8]  = std_ax;
    outFeatures[9]  = mean_ay;
    outFeatures[10] = max_ay;
    outFeatures[11] = std_ay;
    outFeatures[12] = mean_az;
    outFeatures[13] = max_az;
    outFeatures[14] = std_az;
    outFeatures[15] = mean_gx;
    outFeatures[16] = max_gx;
    outFeatures[17] = std_gx;
    outFeatures[18] = mean_gy;
    outFeatures[19] = max_gy;
    outFeatures[20] = std_gy;
    outFeatures[21] = mean_gz;
    outFeatures[22] = max_gz;
    outFeatures[23] = std_gz;
    outFeatures[24] = tilt;
    outFeatures[25] = dynamic_sma;
    outFeatures[26] = jerk_max;
    outFeatures[27] = jerk_mean;
}

/**
 * @brief Acquires one ACC+GYRO sample and emits a vector when ready.
 *
 * First output is produced after window_size samples. Afterwards a new
 * vector is produced every step_size samples using the sliding ring buffer.
 * Magnetometer data is intentionally excluded.
 */
bool getFeatureData(datapacket_features_t *p_data,
                    uint16_t current_counter,
                    uint32_t current_timestamp,
                    uint16_t window_size,
                    uint16_t step_size)
{
    if (p_data == NULL ||
        window_size == 0 ||
        window_size > MAX_FEATURE_WINDOW_SIZE ||
        step_size == 0 ||
        step_size > window_size)
        return false;

    /* FEATURES intentionally uses ACC+GYRO only. */
    LSM6DSO_ReadAcc(&accel_data);
    LSM6DSO_ReadGyro(&gyro_data);

    float ax_g = (float)accel_data.x / LSM6DSO_GRAVITY_SCALE_4G;
    float ay_g = (float)accel_data.y / LSM6DSO_GRAVITY_SCALE_4G;
    float az_g = (float)accel_data.z / LSM6DSO_GRAVITY_SCALE_4G;

    float gx_dps = (float)gyro_data.x * LSM6DSO_GYRO_DPS_PER_LSB_250;
    float gy_dps = (float)gyro_data.y * LSM6DSO_GYRO_DPS_PER_LSB_250;
    float gz_dps = (float)gyro_data.z * LSM6DSO_GYRO_DPS_PER_LSB_250;

    feature_ax[feature_write_index] = process_biquad(&feature_filters[0], ax_g);
    feature_ay[feature_write_index] = process_biquad(&feature_filters[1], ay_g);
    feature_az[feature_write_index] = process_biquad(&feature_filters[2], az_g);
    feature_gx[feature_write_index] = process_biquad(&feature_filters[3], gx_dps);
    feature_gy[feature_write_index] = process_biquad(&feature_filters[4], gy_dps);
    feature_gz[feature_write_index] = process_biquad(&feature_filters[5], gz_dps);

    feature_write_index++;
    if (feature_write_index >= window_size)
        feature_write_index = 0;

    if (feature_valid_samples < window_size)
        feature_valid_samples++;

    if (!feature_first_output_done)
    {
        if (feature_valid_samples < window_size)
            return false;

        /*
         * datapacket_features_t is packed to preserve the exact BLE wire
         * layout. A packed float array is not guaranteed to be naturally
         * aligned, so compute into an aligned local array first and then
         * copy the bytes into the packet.
         */
        float feature_vector[FEATURE_COUNT];
        extractFeatureVector(feature_vector, window_size);
        memcpy(p_data->features,
               feature_vector,
               sizeof(feature_vector));

        p_data->counter = current_counter;
        p_data->timestamp = current_timestamp;

        feature_first_output_done = true;
        feature_samples_since_output = 0;
        return true;
    }

    feature_samples_since_output++;

    if (feature_samples_since_output < step_size)
        return false;

    /*
     * Same alignment rule for all following windows.
     */
    float feature_vector[FEATURE_COUNT];
    extractFeatureVector(feature_vector, window_size);
    memcpy(p_data->features,
           feature_vector,
           sizeof(feature_vector));

    p_data->counter = current_counter;
    p_data->timestamp = current_timestamp;
    feature_samples_since_output = 0;

    return true;
}

// ======================================================================
// ADC AND BATTERY MANAGEMENT
// ======================================================================

/** @brief Required SAADC callback; unused because sampling is blocking. */
void saadc_callback_handler(nrf_drv_saadc_evt_t const *p_event)
{
    (void)p_event;
}

/** @brief Initializes the Nordic SAADC driver. */
void saadc_init(void)
{
    ret_code_t err_code = nrf_drv_saadc_init(NULL, &saadc_callback_handler);
    APP_ERROR_CHECK(err_code);
}

/**
 * @brief Samples battery voltage, maps it to 0-100% and smooths the result.
 */
uint8_t sampleBattery(void)
{
    nrf_saadc_value_t raw;
    ret_code_t err_code;
    int32_t sum = 0;
    static float filtered_percent = BATT_FILTER_INIT_VAL;

    nrf_saadc_channel_config_t cfg_batt =
        NRF_DRV_SAADC_DEFAULT_CHANNEL_CONFIG_SE(BATTERY_ADC_INPUT);

    cfg_batt.gain = NRF_SAADC_GAIN1_6;
    cfg_batt.reference = NRF_SAADC_REFERENCE_INTERNAL;

    err_code = nrf_drv_saadc_channel_init(SAADC_CHANNEL_BATTERY, &cfg_batt);
    APP_ERROR_CHECK(err_code);

    nrf_gpio_pin_set(ADC_ON_PIN);
    nrf_delay_ms(BATT_ADC_SETTLE_TIME_MS);

    for (int i = 0; i < BATT_SAMPLES_COUNT; i++)
    {
        err_code = nrf_drv_saadc_sample_convert(SAADC_CHANNEL_BATTERY, &raw);
        APP_ERROR_CHECK(err_code);
        sum += raw;
    }

    nrf_gpio_pin_clear(ADC_ON_PIN);
    nrf_drv_saadc_channel_uninit(SAADC_CHANNEL_BATTERY);

    int32_t avg_raw = sum / BATT_SAMPLES_COUNT;
    float v_pin = (avg_raw * ADC_REF_VOLTAGE) / ADC_RESOLUTION_10BIT;
    float v_batt = v_pin * BATT_VOLTAGE_DIVIDER_FACTOR;

    float percent;
    if (v_batt <= BATT_VOLTAGE_MIN)
        percent = BATT_PERCENTAGE_MIN;
    else if (v_batt >= BATT_VOLTAGE_MAX)
        percent = BATT_PERCENTAGE_MAX;
    else
        percent = (v_batt - BATT_VOLTAGE_MIN) *
                  BATT_PERCENTAGE_MAX /
                  (BATT_VOLTAGE_MAX - BATT_VOLTAGE_MIN);

    if (filtered_percent < BATT_PERCENTAGE_MIN)
        filtered_percent = percent;
    else
        filtered_percent =
            (BATT_FILTER_ALPHA * percent) +
            ((BATT_FILTER_COMPLEMENT_BASE - BATT_FILTER_ALPHA) * filtered_percent);

    return (uint8_t)filtered_percent;
}

/** @brief Detects USB VBUS presence using the nRF52840 power register. */
power_source_t detectPowerSource(void)
{
    return nrf_power_usbregstatus_vbusdet_get() ? POWER_USB : POWER_BATTERY;
}

// ======================================================================
// SENSORS INITIALIZATION & RAW DATA ACQUISITION
// ======================================================================

/**
 * @brief Initializes LSM6DSO and optional LIS2MDL master-hub acquisition.
 *
 * Every branch intentionally uses explicit braces. This makes the code safer
 * with logging macros and avoids dangling-else/parser issues.
 *
 * @return true when the primary LSM6DSO setup succeeds.
 */
bool setupSensors(void)
{
    NRF_LOG_INFO("Initializing sensors over TWI Master Hub...");

    nrf_delay_ms(SENSOR_INIT_DELAY_MS);

    twi_master_init();

    nrf_delay_ms(SENSOR_INIT_DELAY_MS);

    // Verify communication with the primary LSM6DSO.
    if (!lsm6dso_verify_product_id())
    {
        NRF_LOG_ERROR("LSM6DSO not detected!");
        return false;
    }

    NRF_LOG_INFO("LSM6DSO detected successfully");

    // Reset before applying ODR and full-scale configuration.
    LSM6DSO_RESET();
    nrf_delay_ms(SENSOR_RESET_DELAY_MS);

    // Accelerometer: 104 Hz, ±4 g.
    if (!lsm6dso_accelerometer_init(Hz_104,
                                    acc_fs_sel,
                                    &gravity_scale))
    {
        NRF_LOG_ERROR("Failed to initialize accelerometer");
        return false;
    }
    else
    {
        NRF_LOG_INFO("Accelerometer initialized: 104Hz");
    }

    // Gyroscope: 104 Hz, ±250 dps.
    if (!lsm6dso_gyroscope_init(Hz_104, DPS_250))
    {
        NRF_LOG_ERROR("Failed to initialize gyroscope");
        return false;
    }
    else
    {
        NRF_LOG_INFO("Gyroscope initialized: 104Hz");
    }

    /*
     * The LIS2MDL is optional. RAW mode uses its data when present.
     * FEATURES mode intentionally ignores magnetometer samples.
     */
    if (lis2mdl_check())
    {
        NRF_LOG_INFO("LIS2MDL magnetometer detected");

        lis2mdl_reset();
        nrf_delay_ms(SENSOR_RESET_DELAY_MS);

        if (lis2mdl_init_magnetometer(Hz_104))
        {
            NRF_LOG_INFO("Magnetometer initialized");
        }
        else
        {
            NRF_LOG_WARNING("Failed to initialize magnetometer");
        }

        /*
         * Configure the LSM6DSO sensor hub to fetch the six LIS2MDL
         * output bytes automatically.
         */
        if (lsm6dso_add_sensor(LIS2MDL_ADDRESS,
                               LIS2MDL_OUTX_L_REG,
                               LIS2MDL_DATA_LEN_BYTES))
        {
            NRF_LOG_INFO("LSM6DSO configured as I2C master hub for LIS2MDL");
        }
        else
        {
            NRF_LOG_WARNING("Failed to configure LSM6DSO Master Hub");
        }
    }
    else
    {
        NRF_LOG_WARNING("LIS2MDL magnetometer not found. Running in 6-DoF mode.");
    }

    return true;
}

/**
 * @brief Reads ACC/GYRO/MAG raw values and fills one RAW packet.
 */
void getSensorData(datapacket_t *p_data,
                   uint16_t current_counter,
                   uint32_t current_timestamp)
{
    LSM6DSO_ReadAcc(&accel_data);
    LSM6DSO_ReadGyro(&gyro_data);
    LSM6DSO_WAIT_AND_READ(&magn_data);

    p_data->ax = (int16_t)accel_data.x;
    p_data->ay = (int16_t)accel_data.y;
    p_data->az = (int16_t)accel_data.z;
    p_data->gx = (int16_t)gyro_data.x;
    p_data->gy = (int16_t)gyro_data.y;
    p_data->gz = (int16_t)gyro_data.z;
    p_data->mx = (int16_t)magn_data.x;
    p_data->my = (int16_t)magn_data.y;
    p_data->mz = (int16_t)magn_data.z;
    p_data->counter = current_counter;
    p_data->timestamp = current_timestamp;
}

/** @brief Fills the retained legacy QUAT packet with placeholder values. */
void getQuatData(datapacket_quat_t *p_data,
                 uint16_t current_counter,
                 uint32_t current_timestamp)
{
    p_data->q0 = QUAT_DUMMY_Q0;
    p_data->q1 = QUAT_DUMMY_Q1;
    p_data->q2 = QUAT_DUMMY_Q2;
    p_data->q3 = QUAT_DUMMY_Q3;
    p_data->counter = current_counter;
    p_data->timestamp = current_timestamp;
}
