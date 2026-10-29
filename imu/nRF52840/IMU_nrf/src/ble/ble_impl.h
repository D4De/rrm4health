/**
 * @file ble_impl.h
 * @brief Public BLE interface and custom-service definitions.
 */

#ifndef BLE_IMPL_H
#define BLE_IMPL_H

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "global_defs.h"

#include "nrf_log.h"
#include "nrf_log_ctrl.h"
#include "nrf_log_default_backends.h"
#include "app_timer.h"
#include "bsp_btn_ble.h"
#include "nrf_pwr_mgmt.h"
#include "nrf_sdh.h"
#include "nrf_sdh_ble.h"
#include "nrf_sdh_soc.h"
#include "nrf_ble_gatt.h"
#include "ble_advdata.h"
#include "ble_advertising.h"
#include "ble_conn_params.h"
#include "ble_srv_common.h"
#include "ble_bas.h"

#include "sensors.h"

#define AAAC_KIT_BASE_SRV         {0xE8, 0x74, 0x2C, 0x65, 0xF0, 0x01, 0x38, 0x95, 0x7A, 0x46, 0x00, 0x00, 0x02, 0x00, 0x5A, 0x55}
#define BASE_UUID(VAL1, VAL2)     {0xE8, 0x74, 0x2C, 0x65, 0xF0, 0x01, 0x38, 0x95, 0x7A, 0x46, VAL1, VAL2, 0x02, 0x00, 0x5A, 0x55}

#define UUID_SRV_COMMON           0x0002
#define BASE_UUID_SRV             BASE_UUID(0x00, 0x00)

#define UUID_BASE_CHR_ACK         BASE_UUID(0x10, 0x00)
#define UUID_BASE_CHR_SENSORS     BASE_UUID(0x30, 0x00)
#define UUID_BASE_CHR_QUAT        BASE_UUID(0x31, 0x00)
#define UUID_BASE_CHR_FEATURES    BASE_UUID(0x32, 0x00)
#define UUID_BASE_CHR_TIMESTAMP   BASE_UUID(0x34, 0x00)
#define UUID_BASE_CHR_CAMPCONF    BASE_UUID(0x35, 0x00)
#define UUID_BASE_CHR_ACTIVITY    BASE_UUID(0x40, 0x00)
#define BOOT_ID_BASE_UUID         BASE_UUID(0x99, 0x00)

#define BLE_UUID_BATTERY_SERVICE      0x180F
#define BLE_UUID_BATTERY_LEVEL_CHAR   0x2A19

#define APP_BLE_CONN_CFG_TAG      1
#define APP_BLE_OBSERVER_PRIO     3

typedef volatile uint32_t REG32;
#define pREG32 (REG32 *)
#define MAC_ADDRESS_HIGH    (*(pREG32(0x100000a8)))
#define MAC_ADDRESS_LOW     (*(pREG32(0x100000a4)))

#define MIN_CONN_INTERVAL      MSEC_TO_UNITS(20, UNIT_1_25_MS)
#define MAX_CONN_INTERVAL      MSEC_TO_UNITS(50, UNIT_1_25_MS)
#define SLAVE_LATENCY          0
#define CONN_SUP_TIMEOUT       MSEC_TO_UNITS(4000, UNIT_10_MS)

#define FIRST_CONN_PARMS_UPDATE_DELAY   APP_TIMER_TICKS(5000)
#define NEXT_CONN_PARMS_UPDATE_DELAY    APP_TIMER_TICKS(30000)
#define MAX_CONN_PARMS_UPDATE_COUNT     3

#define APP_ADV_INTERVAL    160
#define APP_ADV_DURATION    0

/** Callback signature for writable custom characteristics. */
typedef void (*ble_cs_write_handler_t)(uint8_t const *p_data, uint16_t len);

/** Initialization parameters for the custom service. */
typedef struct
{
  uint8_t initial_custom_value;
  ble_srv_cccd_security_mode_t custom_value_char_attr_md;
} ble_cs_init_t;

/**
 * Runtime handles, UUID types and callbacks for the custom BLE service.
 */
typedef struct ble_cs_struct
{
  uint16_t service_handle;

  ble_gatts_char_handles_t ack_handles;
  ble_gatts_char_handles_t sensors_handles;
  ble_gatts_char_handles_t quat_handles;
  ble_gatts_char_handles_t features_handles;
  ble_gatts_char_handles_t timestamp_handles;
  ble_gatts_char_handles_t campaign_handles;
  ble_gatts_char_handles_t activity_handles;
  ble_gatts_char_handles_t boot_id_handles;

  uint8_t uuid_type_srv;
  uint8_t uuid_type_ack;
  uint8_t uuid_type_sensors;
  uint8_t uuid_type_quat;
  uint8_t uuid_type_features;
  uint8_t uuid_type_timestamp;
  uint8_t uuid_type_campconf;
  uint8_t uuid_type_activity;
  uint8_t uuid_type_boot_id;

  ble_cs_write_handler_t activity_cb;
  ble_cs_write_handler_t campconf_cb;
  ble_cs_write_handler_t timestamp_cb;
} ble_cs_struct_t;

/** Application callbacks bound to writable custom characteristics. */
typedef struct
{
  ble_cs_write_handler_t activity_cb;
  ble_cs_write_handler_t campconf_cb;
  ble_cs_write_handler_t timestamp_cb;
} ble_custom_callbacks_t;

/** Convert one byte to two hexadecimal characters. */
void byte_to_str(char s[], uint16_t b);
/** Return true when a central is connected. */
bool dataHub_connected(void);
/** Enter low-power idle state when possible. */
void idle_state_handle(void);

/** Initialize SoftDevice BLE stack. */
void ble_stack_init(void);
/** Configure GAP name and preferred connection parameters. */
void gap_params_init(void);
/** Initialize GATT support. */
void gatt_init(void);
/** Configure advertising and scan response. */
void advertising_init(void);
/** Initialize connection-parameter negotiation. */
void conn_params_init(void);
/** Initialize custom service and always-available Battery Service. */
void services_init(ble_custom_callbacks_t *callbacks);

/** Update ACK characteristic. */
void update_ack_char(uint8_t *p_data, uint16_t len);
/** Update BOOT_ID characteristic. */
void update_boot_id_char(uint8_t *p_data, uint16_t len);
/** Update and notify RAW characteristic. */
void update_notify_sensors_char(uint8_t *p_data, uint16_t len);
/** Update and notify legacy QUAT characteristic. */
void update_notify_quat_char(uint8_t *p_data, uint16_t len);
/** Update and notify FEATURES characteristic. */
void update_notify_features_char(uint8_t *p_data, uint16_t len);
/** Update and optionally notify standard Battery Level. */
void update_notify_battery_char(uint8_t *p_data, uint16_t len);

/** Start advertising. */
void advertising_start(void);
/** Stop advertising. */
void advertising_stop(void);
/** Disconnect current central if connected. */
void try_disconnect(void);

#endif