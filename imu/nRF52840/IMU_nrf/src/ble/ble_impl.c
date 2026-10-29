/**
 * @file ble_impl.c
 * @brief BLE stack, custom service, Battery Service and notifications.
 *
 * Custom characteristic mapping:
 *   0010 -> ACK
 *   0030 -> RAW sensors
 *   0031 -> QUAT (legacy/internal)
 *   0032 -> FEATURES
 *   0034 -> TIMESTAMP
 *   0035 -> CAMPAIGN CONFIG
 *   0040 -> ACTIVITY START/STOP
 *   0099 -> BOOT ID
 *
 * Standard Battery Service:
 *   180F -> Battery Service
 *   2A19 -> Battery Level
 *
 * Battery Service is ALWAYS registered so the Python manager can connect
 * only to read battery level, even when no acquisition campaign is active
 * and even when the board booted while externally powered.
 */

#include "ble_impl.h"

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

/** Refreshes Battery Level characteristic immediately after connection. */
/**
 * @brief Samples battery immediately and updates BAS for the active connection.
 */
static void refresh_battery_level(void);

/** Runtime instance of the custom AAAC BLE service. */
static ble_cs_struct_t m_customService;
/** Current central connection handle, or BLE_CONN_HANDLE_INVALID. */
static uint16_t m_conn_handle = BLE_CONN_HANDLE_INVALID;
/** Tracks successful initialization of the standard BAS service. */
static bool m_battery_service_initialized = false;

static ble_uuid_t m_adv_uuids[] = {
    {UUID_SRV_COMMON, BLE_UUID_TYPE_VENDOR_BEGIN},
    {BLE_UUID_BATTERY_SERVICE, BLE_UUID_TYPE_BLE},
};

NRF_BLE_GATT_DEF(m_gatt);
BLE_ADVERTISING_DEF(m_advertising);
BLE_BAS_DEF(m_bas);

/** @brief Handles connection-parameter update results. */
void on_conn_params_evt(ble_conn_params_evt_t *p_evt)
{
  if (p_evt->evt_type == BLE_CONN_PARAMS_EVT_FAILED)
    NRF_LOG_WARNING("The central device failed to accept the requested connection parameters.");

  if (p_evt->evt_type == BLE_CONN_PARAMS_EVT_SUCCEEDED)
    NRF_LOG_INFO("Connection parameters were updated successfully.");
}

/** @brief Error callback for the Nordic connection-parameters module. */
void conn_params_error_handler(uint32_t nrf_error)
{
  APP_ERROR_HANDLER(nrf_error);
}

/** @brief Handles advertising state changes. */
void on_adv_evt(ble_adv_evt_t ble_adv_evt)
{
  ret_code_t err_code;

  switch (ble_adv_evt)
  {
  case BLE_ADV_EVT_FAST:
    NRF_LOG_INFO("Advertising started...");
    err_code = bsp_indication_set(BSP_INDICATE_ADVERTISING);
    APP_ERROR_CHECK(err_code);
    break;

  case BLE_ADV_EVT_IDLE:
    NRF_LOG_INFO("Advertising stopped");
    err_code = bsp_indication_set(BSP_INDICATE_IDLE);
    APP_ERROR_CHECK(err_code);
    break;

  default:
    break;
  }
}

/**
 * @brief Routes custom GATT writes to firmware callbacks.
 *
 * CCCD writes for RAW, QUAT and FEATURES are only logged because the BLE
 * stack itself manages notification enable/disable state.
 */
void on_gatt_write_evt(ble_evt_t const *p_ble_evt, void *p_context)
{
  ble_gatts_evt_write_t const *p_evt_write = &p_ble_evt->evt.gatts_evt.params.write;
  ble_cs_struct_t *p_cs = (ble_cs_struct_t *)p_context;

  if (p_cs == NULL)
    return;

  if (p_evt_write->handle == p_cs->activity_handles.value_handle)
  {
    p_cs->activity_cb(p_evt_write->data, p_evt_write->len);
  }
  else if (p_evt_write->handle == p_cs->campaign_handles.value_handle)
  {
    p_cs->campconf_cb(p_evt_write->data, p_evt_write->len);
  }
  else if (p_evt_write->handle == p_cs->timestamp_handles.value_handle)
  {
    p_cs->timestamp_cb(p_evt_write->data, p_evt_write->len);
  }
  else if (p_evt_write->handle == p_cs->sensors_handles.cccd_handle)
  {
    NRF_LOG_INFO((p_evt_write->len == 2 && p_evt_write->data[0] == 0x01)
                     ? "Notifications enabled for sensors"
                     : "Notifications disabled for sensors");
  }
  else if (p_evt_write->handle == p_cs->quat_handles.cccd_handle)
  {
    NRF_LOG_INFO((p_evt_write->len == 2 && p_evt_write->data[0] == 0x01)
                     ? "Notifications enabled for quat"
                     : "Notifications disabled for quat");
  }
  else if (p_evt_write->handle == p_cs->features_handles.cccd_handle)
  {
    NRF_LOG_INFO((p_evt_write->len == 2 && p_evt_write->data[0] == 0x01)
                     ? "Notifications enabled for features"
                     : "Notifications disabled for features");
  }
  else
  {
    NRF_LOG_DEBUG("Unknown characteristic: 0x%04X", p_evt_write->handle);
  }
}

/**
 * @brief Main SoftDevice BLE event handler.
 *
 * On connection the Battery Level is refreshed immediately so the manager
 * can perform one-shot battery reads even outside acquisition campaigns.
 */
void ble_evt_handler(ble_evt_t const *p_ble_evt, void *p_context)
{
  ret_code_t err_code = NRF_SUCCESS;

  switch (p_ble_evt->header.evt_id)
  {
  case BLE_GAP_EVT_DISCONNECTED:
    NRF_LOG_INFO("Device is disconnected!");
    m_conn_handle = BLE_CONN_HANDLE_INVALID;
    break;

  case BLE_GAP_EVT_CONNECTED:
    NRF_LOG_INFO("Device is connected!");
    err_code = bsp_indication_set(BSP_INDICATE_CONNECTED);
    APP_ERROR_CHECK(err_code);

    m_conn_handle = p_ble_evt->evt.gap_evt.conn_handle;

    if (m_battery_service_initialized)
      refresh_battery_level();
    break;

  case BLE_GAP_EVT_PHY_UPDATE_REQUEST:
  {
    ble_gap_phys_t const phys = {
        .rx_phys = BLE_GAP_PHY_AUTO,
        .tx_phys = BLE_GAP_PHY_AUTO,
    };

    err_code = sd_ble_gap_phy_update(p_ble_evt->evt.gap_evt.conn_handle, &phys);
    APP_ERROR_CHECK(err_code);
    break;
  }

  case BLE_GATTS_EVT_WRITE:
    on_gatt_write_evt(p_ble_evt, &m_customService);
    break;

  default:
    break;
  }
}

/** @brief Converts one byte into two uppercase hexadecimal characters. */
void byte_to_str(char s[], uint16_t b)
{
  uint8_t val = b & 0x0F;
  s[1] = (val < 10) ? ('0' + val) : ('A' + (val - 10));

  val = (uint8_t)(b >> 4);
  s[0] = (val < 10) ? ('0' + val) : ('A' + (val - 10));
}

/** @return true when a BLE central is currently connected. */
bool dataHub_connected(void)
{
  return (m_conn_handle != BLE_CONN_HANDLE_INVALID);
}

/** @brief Sleeps the CPU when no pending log processing remains. */
void idle_state_handle(void)
{
  if (NRF_LOG_PROCESS() == false)
    nrf_pwr_mgmt_run();
}

/** @brief Enables and configures the Nordic SoftDevice BLE stack. */
void ble_stack_init(void)
{
  ret_code_t err_code;

  err_code = nrf_sdh_enable_request();
  APP_ERROR_CHECK(err_code);

  uint32_t ram_start = 0;
  err_code = nrf_sdh_ble_default_cfg_set(APP_BLE_CONN_CFG_TAG, &ram_start);
  APP_ERROR_CHECK(err_code);

  err_code = nrf_sdh_ble_enable(&ram_start);
  APP_ERROR_CHECK(err_code);

  NRF_SDH_BLE_OBSERVER(m_ble_observer, APP_BLE_OBSERVER_PRIO, ble_evt_handler, NULL);
}

/**
 * @brief Configures device name and preferred BLE connection parameters.
 *
 * The advertised IMU name is generated from the final bytes of the device
 * address using the IMUXXXX naming scheme.
 */
void gap_params_init(void)
{
  ret_code_t err_code;
  ble_gap_conn_params_t gap_conn_params;
  ble_gap_conn_sec_mode_t sec_mode;

  BLE_GAP_CONN_SEC_MODE_SET_OPEN(&sec_mode);

  char ble_name[8] = IMU_DEFAULT_NAME;
  uint32_t addr_low = MAC_ADDRESS_LOW;
  byte_to_str(&ble_name[3], (addr_low >> 8) & 0xFF);
  byte_to_str(&ble_name[5], addr_low & 0xFF);

  err_code = sd_ble_gap_device_name_set(&sec_mode, (const uint8_t *)ble_name, strlen(ble_name));
  APP_ERROR_CHECK(err_code);

  memset(&gap_conn_params, 0, sizeof(gap_conn_params));

  gap_conn_params.min_conn_interval = MIN_CONN_INTERVAL;
  gap_conn_params.max_conn_interval = MAX_CONN_INTERVAL;
  gap_conn_params.slave_latency = SLAVE_LATENCY;
  gap_conn_params.conn_sup_timeout = CONN_SUP_TIMEOUT;

  err_code = sd_ble_gap_ppcp_set(&gap_conn_params);
  APP_ERROR_CHECK(err_code);
}

/** @brief Initializes the Nordic GATT module. */
void gatt_init(void)
{
  ret_code_t err_code = nrf_ble_gatt_init(&m_gatt, NULL);
  APP_ERROR_CHECK(err_code);
}

/** @brief Configures automatic connection-parameter negotiation. */
void conn_params_init(void)
{
  ret_code_t err_code;
  ble_conn_params_init_t cp_init;

  memset(&cp_init, 0, sizeof(cp_init));

  cp_init.p_conn_params = NULL;
  cp_init.first_conn_params_update_delay = FIRST_CONN_PARMS_UPDATE_DELAY;
  cp_init.next_conn_params_update_delay = NEXT_CONN_PARMS_UPDATE_DELAY;
  cp_init.max_conn_params_update_count = MAX_CONN_PARMS_UPDATE_COUNT;
  cp_init.start_on_notify_cccd_handle = BLE_GATT_HANDLE_INVALID;
  cp_init.disconnect_on_fail = false;
  cp_init.error_handler = conn_params_error_handler;
  cp_init.evt_handler = on_conn_params_evt;

  err_code = ble_conn_params_init(&cp_init);
  APP_ERROR_CHECK(err_code);
}

/** @brief Builds advertising and scan-response payloads. */
void advertising_init(void)
{
  ret_code_t err_code;
  ble_advertising_init_t init;

  memset(&init, 0, sizeof(init));

  init.advdata.name_type = BLE_ADVDATA_FULL_NAME;
  init.advdata.include_appearance = false;
  init.advdata.flags = BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE;

  init.config.ble_adv_fast_enabled = true;
  init.config.ble_adv_fast_interval = APP_ADV_INTERVAL;
  init.config.ble_adv_fast_timeout = APP_ADV_DURATION;

  init.srdata.uuids_complete.uuid_cnt = sizeof(m_adv_uuids) / sizeof(m_adv_uuids[0]);
  init.srdata.uuids_complete.p_uuids = m_adv_uuids;

  init.evt_handler = on_adv_evt;

  err_code = ble_advertising_init(&m_advertising, &init);
  APP_ERROR_CHECK(err_code);

  ble_advertising_conn_cfg_tag_set(&m_advertising, APP_BLE_CONN_CFG_TAG);
}

/** @brief Registers application callbacks for writable custom characteristics. */
void ble_register_custom_callbacks(ble_custom_callbacks_t *p_callbacks)
{
  if (p_callbacks != NULL)
  {
    m_customService.activity_cb = p_callbacks->activity_cb;
    m_customService.campconf_cb = p_callbacks->campconf_cb;
    m_customService.timestamp_cb = p_callbacks->timestamp_cb;
  }
}

/**
 * @brief Registers vendor-specific base UUIDs and creates the primary service.
 */
uint32_t ble_custom_service_init(ble_cs_struct_t *p_cs, const ble_cs_init_t *p_cs_init)
{
  VERIFY_PARAM_NOT_NULL(p_cs);
  VERIFY_PARAM_NOT_NULL(p_cs_init);

  uint32_t err_code;
  ble_uuid_t ble_uuid;

  memset(p_cs, 0, sizeof(ble_cs_struct_t));

  ble_uuid128_t base_srv = BASE_UUID_SRV;
  ble_uuid128_t base_ack = UUID_BASE_CHR_ACK;
  ble_uuid128_t base_sen = UUID_BASE_CHR_SENSORS;
  ble_uuid128_t base_quat = UUID_BASE_CHR_QUAT;
  ble_uuid128_t base_features = UUID_BASE_CHR_FEATURES;
  ble_uuid128_t base_time = UUID_BASE_CHR_TIMESTAMP;
  ble_uuid128_t base_camp = UUID_BASE_CHR_CAMPCONF;
  ble_uuid128_t base_act = UUID_BASE_CHR_ACTIVITY;
  ble_uuid128_t base_boot_id = BOOT_ID_BASE_UUID;

  err_code = sd_ble_uuid_vs_add(&base_srv, &p_cs->uuid_type_srv); VERIFY_SUCCESS(err_code);
  err_code = sd_ble_uuid_vs_add(&base_ack, &p_cs->uuid_type_ack); VERIFY_SUCCESS(err_code);
  err_code = sd_ble_uuid_vs_add(&base_sen, &p_cs->uuid_type_sensors); VERIFY_SUCCESS(err_code);
  err_code = sd_ble_uuid_vs_add(&base_quat, &p_cs->uuid_type_quat); VERIFY_SUCCESS(err_code);
  err_code = sd_ble_uuid_vs_add(&base_features, &p_cs->uuid_type_features); VERIFY_SUCCESS(err_code);
  err_code = sd_ble_uuid_vs_add(&base_time, &p_cs->uuid_type_timestamp); VERIFY_SUCCESS(err_code);
  err_code = sd_ble_uuid_vs_add(&base_camp, &p_cs->uuid_type_campconf); VERIFY_SUCCESS(err_code);
  err_code = sd_ble_uuid_vs_add(&base_act, &p_cs->uuid_type_activity); VERIFY_SUCCESS(err_code);
  err_code = sd_ble_uuid_vs_add(&base_boot_id, &p_cs->uuid_type_boot_id); VERIFY_SUCCESS(err_code);

  ble_uuid.type = p_cs->uuid_type_srv;
  ble_uuid.uuid = UUID_SRV_COMMON;

  return sd_ble_gatts_service_add(BLE_GATTS_SRVC_TYPE_PRIMARY,
                                  &ble_uuid,
                                  &p_cs->service_handle);
}

/**
 * @brief Adds ACK, RAW, QUAT, FEATURES, TIMESTAMP, CONFIG, ACTIVITY and BOOT_ID.
 */
uint32_t custom_chars_add(ble_cs_struct_t *p_cs, const ble_cs_init_t *p_cs_init)
{
  (void)p_cs_init;
  uint32_t err_code;
  ble_add_char_params_t add_char_params;

  memset(&add_char_params, 0, sizeof(add_char_params));
  add_char_params.uuid = UUID_SRV_COMMON;
  add_char_params.uuid_type = p_cs->uuid_type_ack;
  add_char_params.max_len = 1;
  add_char_params.init_len = 1;
  add_char_params.char_props.read = 1;
  add_char_params.read_access = SEC_OPEN;
  err_code = characteristic_add(p_cs->service_handle, &add_char_params, &p_cs->ack_handles);
  if (err_code != NRF_SUCCESS) return err_code;

  memset(&add_char_params, 0, sizeof(add_char_params));
  add_char_params.uuid = UUID_SRV_COMMON;
  add_char_params.uuid_type = p_cs->uuid_type_sensors;
  add_char_params.max_len = sizeof(datapacket_t);
  add_char_params.init_len = sizeof(datapacket_t);
  add_char_params.char_props.notify = 1;
  add_char_params.cccd_write_access = SEC_OPEN;
  err_code = characteristic_add(p_cs->service_handle, &add_char_params, &p_cs->sensors_handles);
  if (err_code != NRF_SUCCESS) return err_code;

  memset(&add_char_params, 0, sizeof(add_char_params));
  add_char_params.uuid = UUID_SRV_COMMON;
  add_char_params.uuid_type = p_cs->uuid_type_quat;
  add_char_params.max_len = sizeof(datapacket_quat_t);
  add_char_params.init_len = sizeof(datapacket_quat_t);
  add_char_params.char_props.notify = 1;
  add_char_params.cccd_write_access = SEC_OPEN;
  err_code = characteristic_add(p_cs->service_handle, &add_char_params, &p_cs->quat_handles);
  if (err_code != NRF_SUCCESS) return err_code;

  /* FEATURES characteristic: 555A0002-0032-467A-9538-01F0652C74E8 */
  memset(&add_char_params, 0, sizeof(add_char_params));
  add_char_params.uuid = UUID_SRV_COMMON;
  add_char_params.uuid_type = p_cs->uuid_type_features;
  add_char_params.max_len = sizeof(datapacket_features_t);
  add_char_params.init_len = sizeof(datapacket_features_t);
  add_char_params.char_props.notify = 1;
  add_char_params.cccd_write_access = SEC_OPEN;
  err_code = characteristic_add(p_cs->service_handle, &add_char_params, &p_cs->features_handles);
  if (err_code != NRF_SUCCESS) return err_code;

  memset(&add_char_params, 0, sizeof(add_char_params));
  add_char_params.uuid = UUID_SRV_COMMON;
  add_char_params.uuid_type = p_cs->uuid_type_timestamp;
  add_char_params.max_len = TIMESTAMP_HEX_LEN;
  add_char_params.init_len = TIMESTAMP_HEX_LEN;
  add_char_params.char_props.write = 1;
  add_char_params.write_access = SEC_OPEN;
  err_code = characteristic_add(p_cs->service_handle, &add_char_params, &p_cs->timestamp_handles);
  if (err_code != NRF_SUCCESS) return err_code;

  memset(&add_char_params, 0, sizeof(add_char_params));
  add_char_params.uuid = UUID_SRV_COMMON;
  add_char_params.uuid_type = p_cs->uuid_type_campconf;
  add_char_params.max_len = CONFIGURATION_HEX_LEN;
  add_char_params.init_len = CONFIGURATION_HEX_LEN;
  add_char_params.char_props.write = 1;
  add_char_params.write_access = SEC_OPEN;
  err_code = characteristic_add(p_cs->service_handle, &add_char_params, &p_cs->campaign_handles);
  if (err_code != NRF_SUCCESS) return err_code;

  memset(&add_char_params, 0, sizeof(add_char_params));
  add_char_params.uuid = UUID_SRV_COMMON;
  add_char_params.uuid_type = p_cs->uuid_type_activity;
  add_char_params.max_len = ACTIVITY_HEX_LEN;
  add_char_params.init_len = ACTIVITY_HEX_LEN;
  add_char_params.char_props.write = 1;
  add_char_params.write_access = SEC_OPEN;
  err_code = characteristic_add(p_cs->service_handle, &add_char_params, &p_cs->activity_handles);
  if (err_code != NRF_SUCCESS) return err_code;

  memset(&add_char_params, 0, sizeof(add_char_params));
  add_char_params.uuid = UUID_SRV_COMMON;
  add_char_params.uuid_type = p_cs->uuid_type_boot_id;
  add_char_params.char_props.read = 1;
  add_char_params.read_access = SEC_OPEN;
  add_char_params.max_len = sizeof(uint32_t);
  add_char_params.init_len = sizeof(uint32_t);
  add_char_params.p_init_value = NULL;
  err_code = characteristic_add(p_cs->service_handle, &add_char_params, &p_cs->boot_id_handles);
  if (err_code != NRF_SUCCESS) return err_code;

  return NRF_SUCCESS;
}

/**
 * @brief Initializes the custom service and the standard Battery Service.
 *
 * BAS is always registered irrespective of current power source. This is
 * required by BleManager.get_battery_levels().
 */
void services_init(ble_custom_callbacks_t *callbacks)
{
  ret_code_t err_code;
  ble_cs_init_t ble_service_init;

  memset(&ble_service_init, 0, sizeof(ble_service_init));

  err_code = ble_custom_service_init(&m_customService, &ble_service_init);
  APP_ERROR_CHECK(err_code);

  err_code = custom_chars_add(&m_customService, &ble_service_init);
  APP_ERROR_CHECK(err_code);

  ble_register_custom_callbacks(callbacks);

  /* Battery service is ALWAYS present, independently from power source. */
  ble_bas_init_t bas_init;
  memset(&bas_init, 0, sizeof(bas_init));

  bas_init.evt_handler = NULL;
  bas_init.support_notification = true;
  bas_init.p_report_ref = NULL;
  bas_init.initial_batt_level = sampleBattery();
  bas_init.bl_rd_sec = SEC_OPEN;
  bas_init.bl_cccd_wr_sec = SEC_OPEN;
  bas_init.bl_report_rd_sec = SEC_OPEN;

  err_code = ble_bas_init(&m_bas, &bas_init);
  APP_ERROR_CHECK(err_code);

  m_battery_service_initialized = true;

  NRF_LOG_INFO("Battery service initialized with level: %u%%",
               bas_init.initial_batt_level);

  m_adv_uuids[0].type = m_customService.uuid_type_srv;
}

/** @brief Updates a local GATT characteristic value without notifying. */
void update_char_val(uint16_t char_value_handle, uint8_t *p_data, uint16_t len)
{
  if (p_data == NULL)
    APP_ERROR_CHECK(NRF_ERROR_NULL);

  ble_gatts_value_t gatts_value;
  memset(&gatts_value, 0, sizeof(gatts_value));

  gatts_value.len = len;
  gatts_value.offset = 0;
  gatts_value.p_value = p_data;

  ret_code_t err_code =
      sd_ble_gatts_value_set(BLE_CONN_HANDLE_INVALID,
                             char_value_handle,
                             &gatts_value);
  APP_ERROR_CHECK(err_code);
}

/**
 * @brief Sends a notification when connected and CCCD state permits it.
 *
 * Resource/CCCD-related transient errors are intentionally tolerated.
 */
void notify_changed_characteristic(uint16_t charHandle, uint8_t *newValue, uint16_t len)
{
  if (m_conn_handle == BLE_CONN_HANDLE_INVALID)
    return;

  ble_gatts_hvx_params_t params;
  memset(&params, 0, sizeof(params));

  params.type = BLE_GATT_HVX_NOTIFICATION;
  params.handle = charHandle;
  params.p_data = newValue;
  params.p_len = &len;

  ret_code_t err_code = sd_ble_gatts_hvx(m_conn_handle, &params);

  if (err_code != NRF_SUCCESS &&
      err_code != BLE_ERROR_GATTS_SYS_ATTR_MISSING &&
      err_code != NRF_ERROR_INVALID_STATE &&
      err_code != NRF_ERROR_RESOURCES)
  {
    APP_ERROR_CHECK(err_code);
  }
}

/** @brief Updates the readable ACK characteristic. */
void update_ack_char(uint8_t *p_data, uint16_t len)
{
  update_char_val(m_customService.ack_handles.value_handle, p_data, len);
}

/** @brief Updates the readable BOOT_ID characteristic. */
void update_boot_id_char(uint8_t *p_data, uint16_t len)
{
  update_char_val(m_customService.boot_id_handles.value_handle, p_data, len);
}

/** @brief Updates and notifies the RAW sensor characteristic (...0030). */
void update_notify_sensors_char(uint8_t *p_data, uint16_t len)
{
  update_char_val(m_customService.sensors_handles.value_handle, p_data, len);
  notify_changed_characteristic(m_customService.sensors_handles.value_handle, p_data, len);
}

/** @brief Updates and notifies the legacy QUAT characteristic (...0031). */
void update_notify_quat_char(uint8_t *p_data, uint16_t len)
{
  update_char_val(m_customService.quat_handles.value_handle, p_data, len);
  notify_changed_characteristic(m_customService.quat_handles.value_handle, p_data, len);
}

/** @brief Updates and notifies the FEATURES characteristic (...0032). */
void update_notify_features_char(uint8_t *p_data, uint16_t len)
{
  update_char_val(m_customService.features_handles.value_handle, p_data, len);
  notify_changed_characteristic(m_customService.features_handles.value_handle, p_data, len);
}

/**
 * @brief Updates BAS Battery Level and notifies subscribed centrals.
 *
 * Called by the periodic battery timer only when the device is actually
 * battery-powered.
 */
void update_notify_battery_char(uint8_t *p_data, uint16_t len)
{
  (void)len;

  if (!m_battery_service_initialized || p_data == NULL)
    return;

  ret_code_t err_code =
      ble_bas_battery_level_update(&m_bas, p_data[0], BLE_CONN_HANDLE_ALL);

  if (err_code != NRF_SUCCESS &&
      err_code != NRF_ERROR_INVALID_STATE &&
      err_code != NRF_ERROR_RESOURCES &&
      err_code != BLE_ERROR_GATTS_SYS_ATTR_MISSING)
  {
    APP_ERROR_CHECK(err_code);
  }
}

/**
 * @brief Samples battery immediately and updates BAS for the active connection.
 */
static void refresh_battery_level(void)
{
  if (!m_battery_service_initialized ||
      m_conn_handle == BLE_CONN_HANDLE_INVALID)
    return;

  uint8_t battery_level = sampleBattery();

  ret_code_t err_code =
      ble_bas_battery_level_update(&m_bas, battery_level, m_conn_handle);

  if (err_code != NRF_SUCCESS &&
      err_code != NRF_ERROR_INVALID_STATE &&
      err_code != NRF_ERROR_RESOURCES &&
      err_code != BLE_ERROR_GATTS_SYS_ATTR_MISSING)
  {
    APP_ERROR_CHECK(err_code);
  }

  NRF_LOG_INFO("Battery level refreshed: %u%%", battery_level);
}

/** @brief Starts fast connectable advertising. */
void advertising_start(void)
{
  ret_code_t err_code = ble_advertising_start(&m_advertising, BLE_ADV_MODE_FAST);
  APP_ERROR_CHECK(err_code);
}

/** @brief Stops the active advertising set. */
void advertising_stop(void)
{
  ret_code_t err_code = sd_ble_gap_adv_stop(m_advertising.adv_handle);
  APP_ERROR_CHECK(err_code);
}

/** @brief Requests disconnection when a central connection exists. */
void try_disconnect(void)
{
  if (m_conn_handle != BLE_CONN_HANDLE_INVALID)
    sd_ble_gap_disconnect(m_conn_handle, BLE_HCI_CONN_INTERVAL_UNACCEPTABLE);
}