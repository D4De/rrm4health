/**
 * @file main.c
 * @brief Main firmware state machine.
 *
 * Supported public campaign modes:
 *   raw=true  -> RAW notifications on UUID ...0030
 *   raw=false -> FEATURES notifications on UUID ...0032
 *
 * Campaign configuration payload (6 bytes, little-endian):
 *   byte 0    sampling_frequency
 *   byte 1    mode (0x00 RAW, 0x01 FEATURES)
 *   byte 2-3  window_size
 *   byte 4-5  step_size
 *
 * Every campaign starts from counter = 0.
 *
 * Two counters are intentionally kept:
 *   counter       -> number of transmitted packets
 *   sampleCounter -> number of physical IMU samples acquired
 *
 * This separation is required because FEATURES mode may acquire many IMU
 * samples before emitting one feature packet.
 */

#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include "nrf_log.h"
#include "nrf_log_ctrl.h"
#include "nrf_log_default_backends.h"
#include "nrf_pwr_mgmt.h"
#include "nrf_soc.h"
#include "nrf_delay.h"

#include "board_config.h"
#include "global_defs.h"
#include "ble_impl.h"
#include "timers.h"
#include "sensors.h"

/** Current state of the firmware state machine. */
volatile imu_states_t imu_state;
/** Parameters of the active acquisition campaign. */
campaign_parameters_t campaign_settings;

/** Sequential counter attached to transmitted RAW/FEATURES packets. */
uint16_t counter;          /* Packet counter */
/** Number of physical ACC/GYRO samples acquired in the current campaign. */
uint32_t sampleCounter;    /* Physical samples acquired in current campaign */
uint32_t initTimestamp;
timestamp_data_t ts;

volatile bool exchanged_msg[REQ_MSG];
volatile bool blnStart = false;
volatile bool blnStop = false;
volatile bool campaign_ongoing = false;

bool batteryPowered = true;
bool firsttime = true;
bool changestate = false;
bool everConnected = false;
bool unexDisconnected = false;

// ======================================================================
// UTILITY AND TIME HANDLING
// ======================================================================

/** @brief Logs the locally stored date/time. */
void showDate(void)
{
    NRF_LOG_INFO("20%02d-%02d-%02dT%02d:%02d:%02d",
                 ts.yy, ts.mm, ts.dd, ts.HH, ts.MM, ts.SS);
}

/** @brief Converts four big-endian bytes received over BLE into uint32_t. */
uint32_t hex4bytes2ulong(const uint8_t *data)
{
    return ((uint32_t)data[0] << 24) |
           ((uint32_t)data[1] << 16) |
           ((uint32_t)data[2] << 8) |
           ((uint32_t)data[3]);
}

/** @brief Stores the campaign initial UNIX timestamp. */
void setTimestamp(uint32_t ts_val)
{
    initTimestamp = ts_val;
}

/**
 * @brief Computes the campaign timestamp from elapsed physical samples.
 *
 * sampleCounter is used instead of packet counter because FEATURES mode
 * may consume many sensor samples before transmitting one packet.
 */
uint32_t updateCurrentTimestamp(void)
{
    uint32_t elapsedMillis = sampleCounter * campaign_settings.interval;
    return initTimestamp + (elapsedMillis / 1000U);
}

/** @brief Converts a UNIX timestamp into the local timestamp_data_t fields. */
void local_strftime(uint32_t nowts)
{
    uint8_t daysOfMonth[] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};

    uint32_t extraTime;
    uint32_t daysTillNow, numDaysInYear, extraDays, currYear;
    uint8_t isleap;
    int32_t diff;

    daysTillNow = nowts / 86400;
    currYear = 1970;

    while (1)
    {
        isleap = (currYear % 400 == 0 || (currYear % 4 == 0 && currYear % 100 != 0));
        numDaysInYear = 365 + isleap;

        if (daysTillNow < numDaysInYear)
            break;

        daysTillNow -= numDaysInYear;
        currYear += 1;
    }

    ts.yy = (uint8_t)(currYear - 2000);
    extraDays = daysTillNow + 1;

    isleap = (currYear % 400 == 0 || (currYear % 4 == 0 && currYear % 100 != 0));

    ts.mm = 0;
    daysTillNow = 0;
    diff = extraDays - daysTillNow - daysOfMonth[ts.mm];

    while (ts.mm < 12 && diff > 0)
    {
        daysTillNow += (daysOfMonth[ts.mm] + (uint16_t)(isleap * (ts.mm == 1)));
        ts.mm += 1;
        diff = extraDays - daysTillNow - daysOfMonth[ts.mm];
    }

    ts.mm += 1;

    if (extraDays - daysTillNow > 0)
        ts.dd = (uint8_t)(extraDays - daysTillNow);
    else
        ts.dd = daysOfMonth[ts.mm] + (uint8_t)(isleap * (ts.mm == 1));

    extraTime = nowts % 86400;
    ts.HH = (uint8_t)(extraTime / 3600);
    ts.MM = (uint8_t)((extraTime % 3600) / 60);
    ts.SS = (uint8_t)((extraTime % 3600) % 60);
    ts.cents = 0;
}

// ======================================================================
// STATE MACHINE HELPERS
// ======================================================================

/** @brief Writes ACK_OK into the readable ACK characteristic. */
void sendACK_OK(void)
{
    uint8_t ack_val = ACK_OK;
    update_ack_char(&ack_val, ACTIVITY_HEX_LEN);

    NRF_LOG_INFO("Sent ACK_OK");

    exchanged_msg[MSG_ACK] = true;
    changestate = true;
}

/** @brief Writes ACK_KO into the readable ACK characteristic. */
void sendACK_KO(void)
{
    uint8_t ack_val = ACK_KO;
    update_ack_char(&ack_val, ACTIVITY_HEX_LEN);

    NRF_LOG_ERROR("Sent ACK_KO");
}

/** @brief Chooses whether reconnect resumes READY or ACQUISITION. */
void decideNextStateOnReconnect(void)
{
    NRF_LOG_INFO("-------- Resuming BLE communication: Got lost somewhere --------");

    if (campaign_ongoing)
        imu_state = STATE_ACQUISITION;
    else
        imu_state = STATE_READY;

    changestate = true;
    firsttime = true;
    unexDisconnected = false;
}

/** @brief Prints a human-readable representation of imu_state. */
void print_state(void)
{
    switch (imu_state)
    {
    case STATE_POWER_ON:           NRF_LOG_INFO("POWER ON"); break;
    case STATE_WAIT_TIMESTAMP:     NRF_LOG_INFO("WAITING FOR TIMESTAMP"); break;
    case STATE_WAIT_CONFIGURATION: NRF_LOG_INFO("WAITING FOR CONFIGURATION"); break;
    case STATE_SEND_ACK:           NRF_LOG_INFO("SENDING ACK"); break;
    case STATE_READY:              NRF_LOG_INFO("WAITING FOR START"); break;
    case STATE_ACQUISITION:        NRF_LOG_INFO("data ACQUISITION started"); break;
    case STATE_DISCONNECTION:      NRF_LOG_INFO("DISCONNECTED: lost connection to central device"); break;
    case STATE_STOP:               NRF_LOG_INFO("STOPPED by the application/user"); break;
    case STATE_SLEEP:              NRF_LOG_INFO("going into SLEEP waiting for disconnection or restart"); break;
    case STATE_ZOMBIE:             NRF_LOG_INFO("ZOMBIE"); break;
    default:                       NRF_LOG_INFO("Unrecognized state"); break;
    }
}

/** @brief Restores the correct setup state after an interrupted handshake. */
void decideNextStateOnDisconnect(void)
{
    NRF_LOG_INFO("xxxxxxxxxxx Interrupted BLE communication: Got lost somewhere xxxxxxxx");
    print_state();

    if (exchanged_msg[MSG_TS])
    {
        if (exchanged_msg[MSG_CAMP])
        {
            if (exchanged_msg[MSG_ACK])
                imu_state = STATE_READY;
            else
                imu_state = STATE_SEND_ACK;
        }
        else
        {
            imu_state = STATE_WAIT_CONFIGURATION;
        }
    }
}

// ======================================================================
// BLE CHARACTERISTICS WRITE CALLBACKS
// ======================================================================

/** @brief BLE write callback for the TIMESTAMP characteristic. */
void on_char_timestamp_write(uint8_t const *p_data, uint16_t len)
{
    if (len == TIMESTAMP_HEX_LEN)
    {
        uint32_t pTS = hex4bytes2ulong(p_data);

        setTimestamp(pTS);
        local_strftime(pTS);
        showDate();

        exchanged_msg[MSG_TS] = true;

        NRF_LOG_INFO("Timestamp received: %u", pTS);
    }
    else
    {
        NRF_LOG_INFO("Timestamp: Invalid payload length %u", len);
    }
}

/*
 * Current manager format:
 *   <BBHH
 *   byte 0      sampling frequency
 *   byte 1      mode: 0x00 RAW, 0x01 FEATURES
 *   bytes 2..3  window_size uint16 little endian
 *   bytes 4..5  step_size   uint16 little endian
 */
/**
 * @brief BLE write callback for the 6-byte campaign configuration.
 *
 * Validates frequency, public mode mapping, window size and step size,
 * then resets counters and the FEATURES preprocessing state.
 */
void on_char_campconf_write(uint8_t const *p_data, uint16_t len)
{
    if (len != CONFIGURATION_HEX_LEN)
    {
        NRF_LOG_INFO("Configuration: Invalid payload length %u", len);
        return;
    }

    uint8_t freq =
        (p_data[0] == 0) ? DEFAULT_SAMPLING_FREQUENCY : p_data[0];

    uint8_t mode = p_data[1];

    uint16_t window_size =
        (uint16_t)p_data[2] |
        ((uint16_t)p_data[3] << 8);

    uint16_t step_size =
        (uint16_t)p_data[4] |
        ((uint16_t)p_data[5] << 8);

    if (freq > MAX_SUPPORTED_SAMPLING_FREQUENCY)
    {
        NRF_LOG_ERROR("Unsupported sampling frequency: %u Hz", freq);
        sendACK_KO();
        return;
    }

    if (mode != CAMPAIGN_RAW &&
        mode != CAMPAIGN_FEATURES)
    {
        NRF_LOG_ERROR("Unsupported campaign mode: 0x%02X", mode);
        sendACK_KO();
        return;
    }

    if (mode == CAMPAIGN_FEATURES)
    {
        if (window_size == 0 ||
            window_size > MAX_FEATURE_WINDOW_SIZE ||
            step_size == 0 ||
            step_size > window_size)
        {
            NRF_LOG_ERROR("Invalid FEATURES config: window=%u step=%u",
                          window_size,
                          step_size);
            sendACK_KO();
            return;
        }
    }

    campaign_settings.sampling_frequency = freq;
    campaign_settings.interval =
        (uint16_t)((SAMPL_FREQ_ADJ * 1000.0f) /
                   campaign_settings.sampling_frequency);

    if (campaign_settings.interval == 0)
        campaign_settings.interval = 1;

    campaign_settings.raw =
        (mode == CAMPAIGN_RAW);

    campaign_settings.window_size = window_size;
    campaign_settings.step_size = step_size;

    counter = 0;
    sampleCounter = 0;
    resetFeaturePipeline();

    exchanged_msg[MSG_CAMP] = true;

    NRF_LOG_INFO("Campconf received:");
    NRF_LOG_INFO("\tFreq: %u Hz", campaign_settings.sampling_frequency);
    NRF_LOG_INFO("\tInterval: %u ms", campaign_settings.interval);
    NRF_LOG_INFO("\tMode: %s", campaign_settings.raw ? "RAW" : "FEATURES");
    NRF_LOG_INFO("\tWindow: %u", campaign_settings.window_size);
    NRF_LOG_INFO("\tStep: %u", campaign_settings.step_size);

    imu_state = STATE_SEND_ACK;
}

/** @brief BLE write callback for START/STOP campaign commands. */
void on_char_activity_write(uint8_t const *p_data, uint16_t len)
{
    if (len != 1)
        return;

    NRF_LOG_INFO("Start/Stop received");

    if (p_data[0] == START_CAMPAIGN)
    {
        NRF_LOG_INFO("STARTING");

        counter = 0;
        sampleCounter = 0;
        resetFeaturePipeline();

        campaign_ongoing = true;
        blnStart = true;
    }
    else if (p_data[0] == STOP_CAMPAIGN)
    {
        NRF_LOG_INFO("STOPPING");

        if (imu_state == STATE_ACQUISITION ||
            imu_state == STATE_READY)
        {
            blnStop = true;
            campaign_ongoing = false;

            for (int i = 0; i < REQ_MSG; i++)
                exchanged_msg[i] = false;
        }
    }
    else
    {
        NRF_LOG_INFO("Start/Stop: Invalid command 0x%02X", p_data[0]);
    }
}

// ======================================================================
// INITIALIZATIONS
// ======================================================================

/** @brief Initializes Nordic power-management support. */
static void power_management_init(void)
{
    ret_code_t err_code = nrf_pwr_mgmt_init();
    APP_ERROR_CHECK(err_code);
}

/** @brief Initializes the Nordic logging subsystem and backends. */
static void log_init(void)
{
    ret_code_t err_code = NRF_LOG_INIT(NULL);
    APP_ERROR_CHECK(err_code);
    NRF_LOG_DEFAULT_BACKENDS_INIT();
}

/** @brief Reads the unique 64-bit identifier from FICR DEVICEID registers. */
uint64_t getDeviceID()
{
    return ((uint64_t)NRF_FICR->DEVICEID[1] << 32) |
           NRF_FICR->DEVICEID[0];
}

/**
 * @brief Generates a new random boot identifier.
 *
 * Uses the SoftDevice RNG and falls back to DEVICEID XOR timer count if
 * the random pool cannot provide enough bytes.
 */
uint32_t getBootID(void)
{
    uint32_t random_id = 0;
    uint8_t random_bytes[4];
    uint32_t err_code;
    uint8_t retries = 0;

    do
    {
        err_code = sd_rand_application_vector_get(random_bytes, 4);

        if (err_code == NRF_ERROR_SOC_RAND_NOT_ENOUGH_VALUES)
        {
            nrf_delay_ms(5);
            retries++;
        }
    }
    while (err_code == NRF_ERROR_SOC_RAND_NOT_ENOUGH_VALUES &&
           retries < 100);

    if (err_code == NRF_SUCCESS)
    {
        random_id =
            (uint32_t)random_bytes[0] |
            ((uint32_t)random_bytes[1] << 8) |
            ((uint32_t)random_bytes[2] << 16) |
            ((uint32_t)random_bytes[3] << 24);
    }
    else
    {
        random_id =
            (uint32_t)(getDeviceID() ^ app_timer_cnt_get());

        NRF_LOG_ERROR("RNG failed! err_code: 0x%X", err_code);
    }

    return random_id;
}

/**
 * @brief Initializes hardware, sensors, BLE services, timers and state.
 *
 * The Battery Service is always registered. batteryPowered only controls
 * periodic battery polling during an acquisition campaign.
 */
void setup()
{
    log_init();
    power_management_init();

    board_init();
    saadc_init();

    if (!setupSensors())
        NRF_LOG_ERROR("Sensor initialization FAILED!");

    ble_stack_init();
    timers_init();
    gap_params_init();
    gatt_init();

    ble_custom_callbacks_t cbs = {
        .activity_cb = on_char_activity_write,
        .campconf_cb = on_char_campconf_write,
        .timestamp_cb = on_char_timestamp_write,
    };

    batteryPowered =
        detectPowerSource() == POWER_BATTERY;

    /*
     * Battery Service is always registered.
     * batteryPowered only decides whether periodic refresh is needed.
     */
    services_init(&cbs);

    advertising_init();
    conn_params_init();

    uint32_t boot_id = getBootID();
    update_boot_id_char((uint8_t *)&boot_id, sizeof(boot_id));

    NRF_LOG_INFO("BOOT_ID: %u", boot_id);
    NRF_LOG_INFO("Power source: %s",
                 batteryPowered ? "BATTERY" : "USB");
    NRF_LOG_INFO("IMU alive");

    advertising_start();

    counter = DEFAULT_COUNTER_INIT;
    sampleCounter = 0;
    initTimestamp = DEFAULT_TIMESTAMP_INIT;
    campaign_ongoing = false;
    blnStart = false;
    blnStop = false;
    imu_state = STATE_POWER_ON;

    resetFeaturePipeline();

    for (int i = 0; i < REQ_MSG; i++)
        exchanged_msg[i] = false;
}

// ======================================================================
// MAIN LOOP
// ======================================================================

/**
 * @brief Firmware entry point and state-machine loop.
 *
 * Sensor work is performed in the main loop after timer flags are raised,
 * keeping timer callbacks lightweight.
 */
int main(void)
{
    setup();

    for (;;)
    {
        if (firsttime)
        {
            print_state();
            firsttime = false;
        }

        switch (imu_state)
        {
        case STATE_POWER_ON:
        case STATE_WAIT_TIMESTAMP:
            if (exchanged_msg[MSG_TS])
                imu_state = STATE_WAIT_CONFIGURATION;
            break;

        case STATE_WAIT_CONFIGURATION:
            if (exchanged_msg[MSG_CAMP])
                imu_state = STATE_SEND_ACK;
            else
                local_strftime(updateCurrentTimestamp());
            break;

        case STATE_SEND_ACK:
            if (dataHub_connected())
            {
                sendACK_OK();
                imu_state = STATE_READY;
            }
            break;

        case STATE_READY:
            if (!dataHub_connected())
            {
                imu_state = STATE_POWER_ON;
                firsttime = true;
            }
            else if (blnStart)
            {
                blnStop = false;
                imu_state = STATE_ACQUISITION;
                blnStart = false;

                led_on();

                imu_sampling_timer_start(
                    campaign_settings.interval);

                if (batteryPowered)
                    battery_timer_start();
            }
            break;

        case STATE_ACQUISITION:
            if (!dataHub_connected())
            {
                unexDisconnected = true;
                imu_state = STATE_DISCONNECTION;

                imu_sampling_timer_stop();
                battery_timer_stop();
                disconnect_timeout_timer_start();

                led_off();

                changestate = true;
                firsttime = true;
            }
            else if (blnStop)
            {
                imu_sampling_timer_stop();
                battery_timer_stop();

                imu_state = STATE_STOP;
            }
            else
            {
                if (check_and_clear_imu_flag())
                {
                    uint32_t current_timestamp =
                        updateCurrentTimestamp();

                    if (campaign_settings.raw)
                    {
                        datapacket_t raw_packet;

                        getSensorData(
                            &raw_packet,
                            counter,
                            current_timestamp);

                        update_notify_sensors_char(
                            (uint8_t *)&raw_packet,
                            sizeof(raw_packet));

                        counter++;
                    }
                    else
                    {
                        datapacket_features_t feature_packet;

                        if (getFeatureData(
                                &feature_packet,
                                counter,
                                current_timestamp,
                                campaign_settings.window_size,
                                campaign_settings.step_size))
                        {
                            update_notify_features_char(
                                (uint8_t *)&feature_packet,
                                sizeof(feature_packet));

                            /*
                             * Counter tracks transmitted feature packets,
                             * not internal IMU samples.
                             */
                            counter++;
                        }
                    }

                    /*
                     * Physical sample count is independent from packet count.
                     * It is used for the campaign timestamp.
                     */
                    sampleCounter++;
                }

                if (check_and_clear_battery_flag())
                {
                    uint8_t battery_level =
                        sampleBattery();

                    update_notify_battery_char(
                        &battery_level,
                        BATTLEVEL_HEX_LEN);
                }
            }
            break;

        case STATE_STOP:
            led_off();

            imu_state = STATE_SLEEP;
            blnStop = false;
            changestate = true;
            break;

        case STATE_SLEEP:
            if (!dataHub_connected())
            {
                NRF_LOG_INFO("Campaign concluded. Moving to POWER_ON for another campaign");

                imu_state = STATE_POWER_ON;
                everConnected = false;
                changestate = true;
            }
            break;

        case STATE_DISCONNECTION:
            if (!dataHub_connected())
            {
                if (check_and_clear_disconnect_flag())
                {
                    NRF_LOG_INFO("Timeout expired. Disconnecting. Expecting HW Reset.");

                    led_off();
                    advertising_stop();
                    try_disconnect();

                    imu_state = STATE_ZOMBIE;
                }
            }
            else
            {
                disconnect_timeout_timer_stop();

                if (campaign_ongoing)
                {
                    NRF_LOG_INFO("Resuming BLE communication. Going back to ACQUISITION");

                    imu_state = STATE_ACQUISITION;
                    led_on();

                    imu_sampling_timer_start(
                        campaign_settings.interval);

                    if (batteryPowered)
                        battery_timer_start();
                }
                else
                {
                    imu_state = STATE_READY;
                }

                changestate = true;
                firsttime = true;
            }
            break;

        case STATE_ZOMBIE:
            break;

        default:
            if (unexDisconnected)
            {
                if (dataHub_connected())
                    decideNextStateOnReconnect();
                else
                    decideNextStateOnDisconnect();
            }
            break;
        }

        idle_state_handle();
    }
}